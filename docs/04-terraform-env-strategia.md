# Terraform és environment stratégia

## Miért nem 4 külön EKS cluster?

A Terraform egyetlen EKS clustert épít fel. A dev/uat/staging/prod elkülönítés namespace-szinten valósul meg, nem cluster-szinten.

```
1 EKS cluster
├── java-app-dev
├── java-app-uat
├── java-app-staging
└── java-app-prod
```

### Indoklás

**Költség:** 4 EKS cluster = 4x control plane díj ($0.10/óra/cluster), 4x node group, 4x NAT gateway, 4x OpenSearch domain. Namespace-alapú izoláció esetén ezek mind megosztottak.

**Üzemeltetési teher:** 4 cluster frissítése, monitorozása és jogosultságkezelése aránytalanul nagy overhead egy kisebb csapatnál vagy próbafeladatnál.

**Namespace-szintű izoláció elegendő, mert:**
- NetworkPolicy szabályozza a cross-namespace forgalmat
- RBAC-cal a fejlesztők csak a saját env namespacéhez férnek hozzá
- A Helmfile és ArgoCD értékfájljai per-environment kezelik a konfigurációkat
- Resource quota per namespace beállítható, ha kell

### Mikor kellene mégis külön cluster?

- **Compliance / szigorú audit**: ha a prod adatokat fizikailag el kell különíteni (pl. PCI-DSS, ahol a dev forgalom nem mehet át ugyanazon a control plane-en)
- **Különböző Kubernetes verziók**: ha dev-en új K8s verziót tesztelünk mielőtt prod-ra kerül
- **Blast radius**: ha egy cluster-szintű hibától (pl. etcd korrupció, rossz cluster upgrade) teljesen el akarjuk szigetelni a prod-ot

### Hogyan lehetne multi-cluster Terraformot megvalósítani

Ha mégis kellene, Terraform workspace-ekkel vagy külön state fájlokkal oldható meg:

```bash
# Workspace alapú megközelítés
terraform workspace new prod
terraform workspace new staging
terraform apply -var-file=envs/prod.tfvars
```

Vagy külön mappák per cluster:

```
terraform/
  clusters/
    dev/
    staging/
    prod/
```

A jelenlegi setupban ez nem szükséges – a single-cluster, multi-namespace megközelítés a mérethez és a feladathoz arányos.
