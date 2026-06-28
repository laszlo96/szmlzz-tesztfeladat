# Monitoring és Observability

## Monitoring stack

Az egész observability stack Amazon OpenSearch Service-re épül – egyetlen rendszer kezeli a logokat, metrikákat és trace-eket. Az adatokat az OpenTelemetry Collector gyűjti össze és tölti be.

| Komponens | Szerepe |
|---|---|
| Amazon OpenSearch Service | Logok, metrikák, trace-ek tárolása és keresése |
| OpenSearch Dashboards | Vizualizáció, dashboardok (beépített, külön telepítés nélkül) |
| OpenSearch Alerting plugin | Riasztások (beépített) |
| OpenTelemetry Collector | Egységes telemetry pipeline – DaemonSet minden node-on |
| kube-state-metrics | Kubernetes API metrikák exportere |
| node-exporter | Node szintű CPU/memória/lemez metrikák |
| MCP server | Claude-alapú természetes nyelvű lekérdezés fejlesztőknek |

![Monitoring architektúra](../diagrams/3-monitoring/monitoring-architecture.png)

---

## Metrikagyűjtés

### Rétegek

**Infrastruktúra szint:**
- `node-exporter` DaemonSet – CPU, memória, lemez, hálózat node-onként
- `kube-state-metrics` – pod, deployment, node státusz, pending podok száma, replika eltérések

**Alkalmazás szint (image-processor):**
- Spring Boot Actuator + Micrometer automatikusan exportálja a JVM metrikákat (`/actuator/prometheus` endpoint)
- Az OTel Collector scrape-eli ezt a Prometheus receiver-rel és betölti OpenSearch-be
- Saját metrikák: feldolgozott job-ok száma, feldolgozási idő (histogram), hibaarány
- Kafka consumer lag: Strimzi JMX exporter

**Adatbázis szint:**
- CNPG beépített Prometheus endpoint (`/metrics`) – aktív kapcsolatok, replikációs lag, WAL archivál státusz
- Redis: KubeBlocks redis-exporter sidecar – hit/miss ratio, memory kihasználtság

### Hogyan kerülnek az adatok OpenSearch-be

Az OTel Collector Prometheus receiver-rel scrape-eli a fenti endpointokat, majd az `elasticsearch` exporterrel (OpenSearch kompatibilis) `metrics-%Y.%m.%d` indexbe tölti be time-series dokumentumként.

---

## Logkezelés

### Összegyűjtés

Az OTel Collector DaemonSet minden node-on fut. A `filelog` receiver beolvassa a konténer logjait a `/var/log/containers/` könyvtárból, Kubernetes metadatát csatol hozzá (namespace, pod neve, node neve, deployment neve), majd OpenSearch-be tölti.

```yaml
logs_index: logs-%{k8s.namespace.name}-%Y.%m.%d
```

Ez automatikusan különíti el a namespacenként a logokat – pl. `logs-java-app-prod-2024.01.15`, `logs-cnpg-prod-2024.01.15`.

### Index stratégia

| Index | Tartalma | Retention |
|---|---|---|
| `logs-java-app-prod-*` | image-processor alkalmazás logok | 30 nap |
| `logs-monitoring-*` | infra komponensek (OTel, kube-state) | 14 nap |
| `logs-cnpg-prod-*` | PostgreSQL logok | 90 nap (audit miatt) |
| `metrics-*` | Kubernetes + alkalmazás + DB metrikák | 90 nap |
| `traces-*` | OpenTelemetry trace-ek | 14 nap |

ISM (Index State Management) policy automatikusan forgatja és törli a lejárt indexeket – ez az OpenSearch beépített funkciója, külön eszköz nem kell.

### Log formátum

Az `image-processor` JSON formátumban naplóz (`logstash-logback-encoder`). Minden log bejegyzés tartalmaz `traceId` és `spanId` mezőket – így egy logsort egy konkrét kéréshez/Kafka üzenethez lehet visszavezetni.

---

## Tracing

OpenTelemetry Java agent automatikus instrumentáción alapul – a forráskódot nem kell módosítani. Az agent a JVM startup-kor töltődik be és automatikusan instrumentálja:
- Spring MVC (HTTP kérések)
- JDBC (PostgreSQL lekérdezések – látszik melyik query mennyi ideig fut)
- Kafka producer/consumer (end-to-end latency Kafka üzenetenként)
- Redis műveletek

```yaml
env:
  - name: JAVA_TOOL_OPTIONS
    value: "-javaagent:/otel-agent/opentelemetry-javaagent.jar"
  - name: OTEL_SERVICE_NAME
    value: "image-processor"
  - name: OTEL_EXPORTER_OTLP_ENDPOINT
    value: "http://otel-collector.monitoring.svc.cluster.local:4317"
```

Az OTel Collector a trace-eket `traces-*` indexbe tölti. Az OpenSearch Dashboards Trace Analytics nézetben vizualizálható, Jaeger-kompatibilis felületet ad.

**Miért nem AWS X-Ray:** az X-Ray SDK vendor lock-in, az OTel megoldás cserélhető és a logokkal egy helyen kereshető.

---

## Megjelenítés

Az OpenSearch Dashboards az OpenSearch Service részeként jön – nem kell külön telepíteni. Két fő vizualizációs mód:

**TSVB (Time Series Visual Builder)** – metrika dashboardokhoz, time-series grafikonok DSL query alapján. Ugyanazt adja mint a Grafana, csak OpenSearch DSL-lel PromQL helyett.

**Discover** – log exploration, szabad szöveges keresés és szűrés.

**Trace Analytics** – trace vizualizáció, Gantt chart spanenként, latencia bontás service-enként.

---

## Dashboardok

### 1. JVM és alkalmazás dashboard

- Heap/non-heap memória kihasználtság trend
- GC pause time (G1 GC)
- HTTP kérések rate-e és latenciája (p50/p95/p99)
- Kafka consumer lag per partition
- Feldolgozott job-ok száma és hibaaránya

### 2. Kafka dashboard

- Consumer lag per consumer group, per topic, per partition
- Produce/consume throughput
- Strimzi broker metrikák (ISR shrink, leader election)

### 3. PostgreSQL dashboard (CNPG)

- Aktív kapcsolatok száma vs connection pool limit
- Replikációs lag – különösen fontos a PG13 → PG17 migráció alatt
- WAL archivál késés (S3 backup státusz)
- Leggyakoribb/leglassabb lekérdezések (pg_stat_statements alapján)
- Autovacuum futások

### 4. Redis dashboard

- Cache hit/miss ratio
- Memory kihasználtság vs maxmemory
- Sentinel failover események

### 5. Infra / Kubernetes dashboard

- Node CPU/memória kihasználtság (on-demand vs spot node group külön szűrve)
- Pod pending idő – Cluster Autoscaler lassúság jelzője
- PVC kihasználtság (Kafka, Redis, CNPG)
- Spot interruption események (CloudWatch Event alapján)

### 6. SLO dashboard

- Alkalmazás availability (uptime %)
- Kafka lag SLO (< X perc késés)
- PostgreSQL backup SLO (WAL archivál max. késés)

---

## Riasztások

Az OpenSearch Alerting plugin query-alapú riasztásokat tud küldeni – egy monitor megadott időközönként lefuttat egy OpenSearch DSL query-t és ha a feltétel teljesül, értesít. A notifikáció SNS-re megy (channel konfigurációval), onnan Slack vagy PagerDuty.

### Kritikus riasztások (P1)

| Riasztás | Feltétel | Réteg |
|---|---|---|
| Pod crash loop | restart count > 3 az elmúlt 5 percben | Alkalmazás |
| Kafka consumer lag | lag > 10 000 üzenet 5 percig | Alkalmazás |
| PostgreSQL replikációs lag | > 60 MB | Adatbázis |
| WAL archivál megáll | 30 percig nincs archivált WAL szegmens | Adatbázis |
| Node NotReady | > 2 perc | Infrastruktúra |
| PVC 90% teli | Kafka / PostgreSQL / Redis | Infrastruktúra |

### Figyelmeztető riasztások (P2)

| Riasztás | Feltétel | Réteg |
|---|---|---|
| Heap kihasználtság | > 80% 10 percig | Alkalmazás |
| HTTP 5xx error rate | > 1% 5 percig | Alkalmazás |
| Redis cache miss rate | < 60% hit ratio 15 percig | Alkalmazás |
| Spot node interruption | CloudWatch Event alapján | Infrastruktúra |

### Migráció-specifikus riasztások (PG13 → PG17 alatt)

A logikai replikáció ideje alatt két extra monitor aktív:
- Logikai replikáció slot lag > 100 MB – a subscriber elmarad, migration window veszélyben
- Sequence drift figyelmeztetés – cutover előtt jelzi ha a sequence szinkronizáció kihagyódott

---

## Infra / alkalmazás / adatbázis szétválasztás

**Index szinten:** a namespace-alapú index naming (`logs-java-app-prod-*`, `logs-cnpg-prod-*`) természetesen különíti el a rétegeket. A DBA csak a `logs-cnpg-prod-*` és `metrics-*` indexekhez kap olvasási jogot, a fejlesztő az app indexekhez.

**OpenSearch fine-grained access control:** index pattern alapján adható jog, pl.:
- `developer` role: `logs-java-app-*`, `traces-*` – olvasás
- `dba` role: `logs-cnpg-*`, `metrics-*` – olvasás
- `ops` role: minden index – olvasás, ISM policy kezelés

**Riasztásoknál:** az infra szintű riasztások (node, PVC) az ops teamhez mennek külön SNS topicra, az alkalmazás szintűek a fejlesztő teamhez.

---

## Hibakeresés

### Tipikus folyamat

1. **Riasztás** jön: Kafka consumer lag megugrott
2. OpenSearch Dashboards **Kafka dashboard**: lag nő, de a pod CPU normális
3. **Discover** nézet, szűrés: `k8s.namespace.name: java-app-prod AND level: ERROR` → `S3ConnectionTimeout` logok jelennek meg
4. **Trace Analytics**: a lassú üzenetek trace-ei megmutatják az S3 hívás spanját, ami timeout-ol
5. Root cause: S3 endpoint throttling → IAM policy rate limit vagy VPC endpoint hiány

### Correlation ID

A `traceId` mező minden logban és trace spanban jelen van – egy kattintással ugrik a fejlesztő a Discover nézetből a Trace Analytics nézetbe a konkrét kérés spanjaira.

---

## Kapacitástervezés

**Alkalmazás skálázás:**
- A Kafka consumer lag metrika OpenSearch-ben idősorozatként tárolódik – visszanézhető mikor volt peak, ebből tervezhető a HPA `minReplicas` hangolása
- Ha a lag konzisztensen magas terhelés alatt, KEDA-val (Kubernetes Event-driven Autoscaling) a HPA triggere lehet maga a lag, nem a CPU

**Adatbázis kapacitás:**
- `pg_database_size()` trend 30 napos ablakban megmutatja mikor kell PVC-t bővíteni
- Connection pool kihasználtság trend: ha konzisztensen > 80%, pgBouncer bevezetése javasolt

**Node szintű tervezés:**
- CNPG + Kafka + Redis memory footprint összesítve meghatározza a szükséges on-demand node-ok számát
- Spot interruption rate historikus adatából látszik melyik instance type a legstabilabb – az `instance_types` lista ennek alapján hangolható

---

## MCP server – fejlesztői lekérdező felület

### Mire való

A fejlesztők természetes nyelven kérdezhetnek rá az OpenSearch indexekre Claude-on keresztül, anélkül hogy ismernék az OpenSearch DSL-t.

**Példa kérések:**
- „Mutasd az elmúlt 1 óra ERROR logjait a prod image-processor-ból"
- „Hány job dolgozódott fel sikeresen ma?"
- „Melyek a leglassabb PostgreSQL lekérdezések az elmúlt 24 órában?"
- „Volt-e crash az elmúlt héten?"

### Elérhető tool-ok

| Tool | Leírás |
|---|---|
| `search_logs` | Szabad szöveges log keresés namespace/level/időablak szűrőkkel |
| `get_error_summary` | ERROR logok összesítése pod szinten, mintaüzenetekkel |
| `get_trace` | Egy trace részleteinek lekérdezése trace ID alapján |
| `get_slow_queries` | Leglassabb PostgreSQL lekérdezések listája |

### Architektúra

Az MCP server `mcp-server` namespaceben fut, ClusterIP service-ként. NetworkPolicy csak a `java-app-prod` namespacéből engedélyezi az elérést (VPN-en belüli hozzáférés). OpenSearch-hez IRSA-val csatlakozik, csak olvasási joggal.

A kód és a Helm chart a `k8s/modules/mcp-server/` könyvtárban van.
