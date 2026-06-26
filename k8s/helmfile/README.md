# helmfile

CNPG operator és PostgreSQL cluster deploymentje helmfile-lal, környezetenként külön values-szal.

## Struktúra

```
helmfile.yaml               # belépési pont, environments + helmfile-ok listája
operator.helmfile.yml       # CNPG operator (cnpg-system namespace)
postgresql.helmfile.yml     # PG13 cluster
postgresql-v17.helmfile.yml # PG17 cluster – csak migráció alatt aktív
values/
  dev/uat/staging/prod/     # környezetenkénti values
```

## Használat

```bash
helmfile -e prod sync        # teljes stack deploy
helmfile -e dev diff         # mi változna
helmfile -e prod apply -f postgresql.helmfile.yml  # csak a cluster
```

Staging és prod erőforrásban azonos (preprod), de különböző S3 bucket és backup retention.
A v17 helmfile a `helmfile.yaml`-ban kommentben van – migráció idején kell kikommentezni.
