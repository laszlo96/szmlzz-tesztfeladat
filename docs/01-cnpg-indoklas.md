# Miért CNPG és nem RDS?

A PostgreSQL clustert CloudNativePG operatorral kezeljük EKS-en, nem AWS RDS-sel.

## Az indok

A helmfile struktúrában van `cnpg/cloudnative-pg` Helm chart – az operátor telepítése és a cluster konfigurálása így ugyanolyan GitOps folyamatba illeszkedik mint bármelyik más alkalmazás. Nem kell külön Terraform-ban RDS erőforrásokat kezelni, és nem kell két különböző rendszerben gondolkodni.

## Ami miatt érdemes CNPG-t választani

Az adatbázis K8s-ben él, ugyanúgy monitorozható, loggolható és deployolható mint a többi workload. A backup S3-ra megy barman-cloud-dal, WAL archiválással és PITR-rel – ez RDS-sel is megvan, de itt mi kontrolláljuk. Failover automatikus, a primary election az operátor dolga.

A logikai replikáció alapú verzióváltás (PG13 → PG17) is az operátoron belül oldható meg, külön infrastruktúra nélkül.

## Mire kell figyelni

Az operátor verziója és a cluster chart verziója össze kell hogy passzoljon – frissítésnél mindkettőt egyszerre érdemes emelni és staging-en előbb kipróbálni. Storage class-t (`gp3`) előre kell gondolni, mert utólag méretezni lehet, de típust változtatni nem.
