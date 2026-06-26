# Helmfile vs ArgoCD

Mindkettő GitOps-kompatibilis megoldás Helm chart-ok kezelésére, de más szinten oldják meg a problémát.

## Helmfile

A Helmfile egy CLI wrapper a Helm fölé. Lokálisan vagy CI/CD pipeline-ból futtatható, nincs cluster-oldali komponens. Egyszerűbb és kevesebb a függőség.
Hasonló eset mint pl. gitlab runner vs gitlab agent esetében, ahol a gitlab runner egyszerűbb felépítést tesz lehetővé.

**Előnyök**
- Gyors bevezetés, nincs extra infrastruktúra
- Könnyen debuggolható (`helmfile diff`, `helmfile template`)
- Jól illeszkedik meglévő CI/CD pipeline-okba (GitHub Actions, GitLab CI)
- Környezetenkénti értékek kezelése tiszta és átlátható

**Hátrányok**
- Nincs live sync – ha valaki kézzel módosít valamit a clusteren, nem veszi észre (operátorok használata emiatt javasolt)
- A futtatás emberen vagy pipeline-on múlik, nincs folyamatos reconciliation
- Több cluster kezelése bonyolultabb

---

## ArgoCD

Az ArgoCD egy K8s-ben futó operátor, ami folyamatosan figyeli a Git repót és szinkronizálja a cluster állapotát. A deploy nem manuális döntés, hanem automatikus következménye a Git változásnak.

**Előnyök**
- Folyamatos reconciliation – ha valaki kézzel változtat a clusteren, ArgoCD visszaállítja
- Vizuális UI, azonnal látszik mi van deployolva és mi tér el a Git-től
- Multi-cluster kezelés beépített
- Rollback = git revert, audit trail automatikus

**Hátrányok**
- Extra infrastruktúra kell (ArgoCD maga is fut a clusteren)
- Bonyolultabb, nagyobb felkészülést/tanulást igényel, több fogalom (Application, AppSet, Projects, RBAC)
- Secrets kezelése külön megoldást igényel (pl. Sealed Secrets, External Secrets)

---

## Mikor melyiket?

A kettő nem zárja ki egymást – van ahol Helmfile-lal bootstrappelik az ArgoCD-t, aztán ArgoCD veszi át a többi release kezelését.
