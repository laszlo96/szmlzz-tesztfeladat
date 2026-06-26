# PostgreSQL 13 → 17 migráció

## Összefoglalás

A cél egy meglévő CNPG-alapú PostgreSQL 13 cluster migrálása PostgreSQL 17-re AWS EKS-en futó környezetben, ahol 3 alkalmazás használja az adatbázist. A választott megközelítés logikai replikáció, amellyel a tényleges leállási idő másodpercekre csökkenthető egy tervezett karbantartási ablakban.

---

## Migrációs stratégiák összehasonlítása

| Módszer | Leállás | Komplexitás | Rollback |
|---|---|---|---|
| `pg_upgrade` in-place | Hosszú (percek–órák) | Alacsony | Nehéz |
| Dump / restore | Hosszú (DB méretétől függ) | Alacsony | Egyszerű (régi dump megvan) |
| Logikai replikáció | Rövid (30s–2 perc) | Közepes | Egyszerű (PG13 cluster megmarad) |
| CNPG import bootstrap | Közepes (DB méretétől függ) | Alacsony | Egyszerű |

**Választás: logikai replikáció**

Indoklás: a 3 alkalmazás miatt az állásidőt minimalizálni kell. A logikai replikáció lehetővé teszi, hogy a PG17 cluster addig szinkronban legyen a PG13-mal, amíg a cutover meg nem történik. Az in-place `pg_upgrade` CNPG-n nem támogatott, a dump/restore pedig a DB méretétől függően hosszú leállást igényelne.

---

## A jelenlegi környezet felmérése

A migráció előtt az alábbi ellenőrzések szükségesek a PG13 clusteren:

```sql
-- Deprecated funkciók és eltávolított szintaxis ellenőrzése
SELECT * FROM pg_stat_user_tables ORDER BY n_live_tup DESC;

-- Extension-ök és verziójuk
SELECT name, default_version, installed_version FROM pg_available_extensions
WHERE installed_version IS NOT NULL;

-- Aktív replikációs slotok (ne maradjanak lógó slotok)
SELECT slot_name, active, restart_lsn FROM pg_replication_slots;

-- Adatbázis-lista (minden DB-t migrálni kell)
SELECT datname FROM pg_database WHERE datistemplate = false;
```

PG13 → PG17 között eltávolított/változott dolgok amire figyelni kell:
- `pg_stat_activity.wait_event_type` értékek változtak
- `lo_compat_privileges` GUC eltávolítva
- `jsonb` operátorok módosultak egyes edge case-ekben
- Extension-ök (pl. `pg_partman`, `PostGIS`) PG17-kompatibilis verziót igényelhetnek

---

## A migráció lépései

### 1. Backup ellenőrzése (migráció előtt)

A CNPG barman backup-ot használ S3-ra. Migráció előtt ellenőrizni kell, hogy a backup működik és visszaállítható:

```bash
# Backup státusz
kubectl exec -n cnpg-prod cnpg-cluster-1 -- \
  barman-cloud-backup-list s3://my-bucket/cnpg/prod

# WAL archiválás késése
kubectl get cluster cnpg-cluster -n cnpg-prod -o jsonpath='{.status.currentPrimaryFailingSinceTimestamp}'
```

A backup-ot a cutover előtti utolsó pillanatban is le kell futtatni.

### 2. PG13 felkészítése logikai replikációra

A `wal_level: logical` és `max_replication_slots` már be van állítva a helmfile values-ban (prod és staging). A helmfile apply után CNPG rolling restartot végez:

```bash
helmfile -e prod apply -f postgresql.helmfile.yml
```

Ezt követően manuálisan létre kell hozni a publication-t **minden egyes adatbázisban** amit a 3 alkalmazás használ:

```bash
# app1 adatbázisán
kubectl exec -n cnpg-prod cnpg-cluster-1 -- \
  psql -U postgres -d app1_db -c "CREATE PUBLICATION all_tables FOR ALL TABLES;"

# app2 adatbázisán
kubectl exec -n cnpg-prod cnpg-cluster-1 -- \
  psql -U postgres -d app2_db -c "CREATE PUBLICATION all_tables FOR ALL TABLES;"

# app3 adatbázisán
kubectl exec -n cnpg-prod cnpg-cluster-1 -- \
  psql -U postgres -d app3_db -c "CREATE PUBLICATION all_tables FOR ALL TABLES;"
```

### 3. PG17 cluster deploy

A `helmfile.yaml`-ban kikommentezni a v17 release-t:

```yaml
helmfiles:
  - path: operator.helmfile.yml
  - path: postgresql.helmfile.yml
  - path: postgresql-v17.helmfile.yml  # uncomment here
```

A `values/prod/postgresql-v17.yaml`-ban a subscription connection stringjét Secret-ből kell olvasni, nem plaintext-ként. Ezért a `postInitApplicationSQL` helyett egy Kubernetes Job végzi el a subscription létrehozását a cutover előtt:

```yaml
# k8s/cnpg/pg17-subscription-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: pg17-create-subscriptions
  namespace: cnpg-prod
spec:
  template:
    spec:
      restartPolicy: OnFailure
      containers:
        - name: psql
          image: ghcr.io/cloudnative-pg/postgresql:17.4
          env:
            - name: PGPASSWORD
              valueFrom:
                secretKeyRef:
                  name: cnpg-superuser-secret
                  key: password
          command:
            - bash
            - -c
            - |
              for DB in app1_db app2_db app3_db; do
                psql -h cnpg-cluster-v17-rw.cnpg-prod.svc.cluster.local \
                     -U postgres -d $DB -c "
                  CREATE SUBSCRIPTION pg13_sub_${DB}
                  CONNECTION 'host=cnpg-cluster-rw.cnpg-prod.svc.cluster.local
                              port=5432 dbname=${DB} user=postgres
                              password=$(PGPASSWORD) sslmode=require'
                  PUBLICATION all_tables;
                "
              done
```

### 4. Replikáció ellenőrzése

A subscription létrehozása után a PG17 elvégzi az initial sync-et (összes táblát átmásolja), majd folyamatosan replikál. A lag figyelése:

```bash
# PG17-en futtatni
kubectl exec -n cnpg-prod cnpg-cluster-v17-1 -- \
  psql -U postgres -c "
    SELECT subname, received_lsn, latest_end_lsn,
           (latest_end_lsn - received_lsn) AS lag
    FROM pg_stat_subscription;
  "
```

A cutover csak akkor indítható, ha a lag értéke 0 vagy közel nulla.

---

## Éles átállás (cutover)

Ez a rövid leállási ablak. Tervezett karbantartási ablakban, alacsony forgalmú időszakban kell végrehajtani.

### Karbantartási idősáv és rollback határidő

Példa:
- **Karbantartási ablak:** 02:00 – 02:30
- **Cutover indítása:** 02:00
- **Rollback határidő:** 02:15 – ha 15 percen belül nem stabil az új környezet, visszaállítás PG13-ra
- **Ablak vége:** 02:30 – ha minden stabil, a csapat leáll

A rollback határidő azért kritikus, mert minél több idő telik el a cutover után, annál több adat keletkezik PG17-en ami visszaállításkor elvész. A 15 perces határidő egy reális kompromisszum: elég idő a smoke testre, de az esetleges adatvesztési ablak még kezelhető méretű marad.

### Lépések sorban

**1. Appok leállítása** – a 3 alkalmazás replica count-ját 0-ra kell állítani, hogy ne keletkezzen új írás:

```bash
kubectl scale deployment app1 app2 app3 -n app-prod --replicas=0
```

**2. Megvárni hogy a replikációs lag elérje a 0-t:**

```bash
kubectl exec -n cnpg-prod cnpg-cluster-v17-1 -- \
  psql -U postgres -c "SELECT subname, received_lsn, latest_end_lsn FROM pg_stat_subscription;"
```

**3. Sequence-ek szinkronizálása** – a logikai replikáció nem replikálja a sequence értékeket, ezért manuálisan kell átvinni:

```bash
# PG13-on: lekérdezni az aktuális értékeket
kubectl exec -n cnpg-prod cnpg-cluster-1 -- \
  psql -U postgres -d app1_db -t -c "
    SELECT 'SELECT setval(''' || sequencename || ''', ' || last_value || ', true);'
    FROM pg_sequences WHERE schemaname NOT IN ('pg_catalog','information_schema');
  " > /tmp/sequences_app1.sql

# PG17-en: alkalmazni
kubectl exec -n cnpg-prod cnpg-cluster-v17-1 -- \
  psql -U postgres -d app1_db < /tmp/sequences_app1.sql
```

Ezt minden adatbázisra meg kell ismételni.

**4. Connection string átállítás**

Az alkalmazások a `cnpg-cluster-rw` service-re mutatnak. Két lehetőség:

- **A) ConfigMap/Secret frissítés + rolling restart**: minden appnál frissíteni a DB_HOST értékét `cnpg-cluster-v17-rw`-re
- **B) Kubernetes Service átnevezés**: a régi `cnpg-cluster-rw` service-t átirányítani a PG17 podokra (ExternalName vagy selector módosítás)

A B opció gyorsabb és az appokat nem kell újra deployolni, de CNPG-managed service-eknél nem mindig lehetséges.

**5. Appok újraindítása:**

```bash
kubectl scale deployment app1 app2 app3 -n app-prod --replicas=3
```

**6. Smoke test** – minden alkalmazáson ellenőrizni az alap funkcionalitást.

---

## Migráció utáni ellenőrzések

```sql
-- PG verzió
SELECT version();

-- Tábla sorok száma (összevetni PG13 értékekkel)
SELECT schemaname, tablename, n_live_tup
FROM pg_stat_user_tables ORDER BY n_live_tup DESC;

-- Index érvényesség
SELECT indexrelid::regclass, indisvalid FROM pg_index WHERE NOT indisvalid;

-- Aktív kapcsolatok
SELECT count(*), state FROM pg_stat_activity GROUP BY state;

-- Sequence értékek helyesek-e
SELECT sequencename, last_value FROM pg_sequences WHERE schemaname = 'public';
```

Az alkalmazások szintjén:
- API health check endpoint-ok válaszolnak
- DB read/write műveletek működnek
- Nincs constraint violation vagy sequence conflict a logokban

---

## Backup és visszaállítás

A CNPG barman-cloud-t használ WAL archiválásra és base backup-ra S3-on. Ez két visszaállítási lehetőséget ad:

### Teljes restore

Új cluster-t kell létrehozni, ahol a bootstrap recovery a meglévő S3 backup-ra mutat:

```yaml
cluster:
  bootstrap:
    recovery:
      source: cnpg-cluster-backup
  externalClusters:
    - name: cnpg-cluster-backup
      barmanObjectStore:
        destinationPath: s3://my-bucket/cnpg/prod
        s3Credentials:
          accessKeyId:
            name: cnpg-s3-secret
            key: ACCESS_KEY_ID
          secretAccessKey:
            name: cnpg-s3-secret
            key: ACCESS_SECRET_KEY
```

A CNPG letölti az utolsó base backup-ot, majd visszajátssza a WAL-t a legfrissebb állapotig.

### PITR – visszaállítás adott időpontra

Ha például egy rossz migráció vagy törlés előtti állapotba kell visszamenni:

```yaml
cluster:
  bootstrap:
    recovery:
      source: cnpg-cluster-backup
      recoveryTarget:
        targetTime: "2025-06-26 01:55:00"
```

A `targetTime` előtt keletkezett összes tranzakció visszakerül, az utána keletkezők nem. Érdemes ezt staging-en is tesztelni, hogy a WAL archív valóban folyamatos és visszajátszható legyen.

---

## Rollback terv

A PG13 cluster a cutover után is fut, addig amíg a migráció sikeresnek nincs nyilvánítva. Ha probléma van:

1. Appokat leállítani (`replicas=0`)
2. Connection string visszaállítani `cnpg-cluster-rw`-re (PG13)
3. Appokat újraindítani
4. PG17 clustert törölni (`helmfile -e prod destroy -f postgresql-v17.helmfile.yml`)
5. Kivizsgálni a problémát, majd újra tervezni

A PG13 cluster csak akkor törölhető, ha a PG17 legalább 24–48 órán át stabilan fut prodban.

> **Adatvesztési kockázat:** A logikai replikáció egyirányú – a PG17-en a cutover után keletkezett adatok nem kerülnek vissza PG13-ra. Ha a rollback nem azonnal (perceken belül) történik, hanem pl. órákkal később, az adatvesztés elkerülhetetlenül dump/restore-ral oldható meg: PG17-ről pg_dump, majd restore PG13-ra. Ez időigényes és maga is leállással jár. Ha az adatvesztés semmilyen körülmények között nem vállalható, a PG13 clustert mindaddig fenn kell tartani és a rollback procedúrát előre le kell tesztelni staging-en.

---

## Kockázatok és mérséklésük

| Kockázat | Valószínűség | Hatás | Mérséklés |
|---|---|---|---|
| Sequence conflict (duplikált ID) | Magas | Kritikus | Sequence szink cutover előtt kötelező |
| Extension inkompatibilitás PG17-en | Közepes | Magas | Előre tesztelni staging-en |
| Replikációs lag nem éri el 0-t | Közepes | Közepes | Cutover csak akkor, ha lag < 1MB |
| Subscription megszakad initial sync közben | Alacsony | Közepes | DROP/CREATE SUBSCRIPTION újraindítja |
| App nem csatlakozik PG17-höz (SSL, auth) | Alacsony | Magas | Staging-en tesztelni az összes appot |
| Hosszabb leállás mint tervezett | Alacsony | Közepes | Rollback küszöb: ha 10 percen belül nem stabil, visszaállítás |
| Adatvesztés rollback esetén | Magas | Kritikus | Rollback határidő betartása (15 perc), utána csak dump/restore |
| DDL változás a migráció alatt | Alacsony | Magas | Schema freeze a cutover előtt – deploy freeze a karbantartási ablak alatt |
| PG17 viselkedésbeli különbségek (query planner, default értékek) | Közepes | Közepes | Staging-en terheléses teszt, slow query log figyelése az első napokban |

---

## Tesztelés staging-en

Minden lépést staging-en kell először végrehajtani, ahol a setup prod-dal megegyező erőforrásokkal fut. A staging migrációból tanulságokat kell levonni:

- Mennyi ideig tart az initial sync (ebből becsülhető a prod ideje)
- Milyen sequence értékek kerülnek át
- Az appok valóban csatlakoznak-e PG17-höz
- A rollback tényleg működik-e

Staging sikeres migrációja után lehet prod-on végrehajtani.
