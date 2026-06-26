# CLAUDE.md

## A projektről

DevOps Engineer próbafeladat. 3 feladatból áll:
1. PostgreSQL 13 → 17 migráció
2. Kubernetes-környezet Java alkalmazáshoz
3. Monitoring, observability, riasztás

Tech stack: AWS EKS, CNPG, Terraform, Helmfile, ArgoCD.

## Stílus és nyelv

- Dokumentáció magyarul
- Lényegretörő megfogalmazás, felesleges körülírás nélkül

## Projekt konvenciók

- Környezetek: `dev`, `uat`, `staging`, `prod` – a staging erőforrásban prod-szintű (preprod)
- Helmfile és ArgoCD mapák teljesen standalone – nem hivatkoznak egymásra
- Adatbázis: CNPG operator, nem RDS (indoklás: `docs/01-cnpg-indoklas.md`)
- Commit message: Conventional Commits (`feat:`, `docs:`, `fix:` stb.), szóközzel, kötőjel nélkül

## Mappastruktúra

```
docs/          – dokumentáció (markdown)
diagrams/      – architektúraábrák (.mmd + .png)
k8s/
  helmfile/    – Helmfile-alapú GitOps
  argocd/      – ArgoCD-alapú GitOps (standalone)
terraform/     – EKS cluster, egyéb AWS infrastruktúra
```

## Docx generálás

Ha a felhasználó docx exportot kér, pandoc-kal generáld:

```bash
pandoc docs/fajlnev.md -o docs/fajlnev.docx
```

Több fájl egybe:

```bash
pandoc docs/*.md -o output.docx
```

Előfeltétel: `sudo apt install pandoc`

---

## Döntések amiket ne írj felül

- Staging = prod erőforrás
- CNPG-t használunk, nem RDS-t
- PG13 → PG17 migráció: logikai replikáció + blue-green deployment
- Diagramok: Mermaid (.mmd) forrás + renderelt PNG együtt
- PNG generálás: `mmdc -i input.mmd -o output.png -p <(echo '{"args":["--no-sandbox"]}')`
  - Előfeltétel: `sudo npm install -g @mermaid-js/mermaid-cli` és `npx puppeteer browsers install chrome-headless-shell`
