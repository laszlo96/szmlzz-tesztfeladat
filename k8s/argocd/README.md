# argocd

Ugyanaz a CNPG setup mint a helmfile mappában, de ArgoCD-vel kezelve. A két mappa teljesen független – vagy az egyiket vagy a másikat használjuk, nem mindkettőt egyszerre.

## Struktúra

```
applicationsets/
  operator-appset.yaml      # CNPG operator – mind4 env egy ApplicationSet-ben
  postgresql-appset.yaml    # PG13 cluster – mind4 env
apps/
  postgresql-v17-prod.yaml  # PG17 cluster – csak prod, csak migráció idején
values/
  dev/uat/staging/prod/     # környezetenkénti values
```

## Alkalmazás

Az ApplicationSet-eket az ArgoCD-t futtató clusteren kell apply-olni:

```bash
kubectl apply -f applicationsets/ -n argocd
```

A v17 Application csak akkor kerül apply-ra, ha a PG13 → PG17 migráció aktív. Migráció után törölni kell.

## Cluster URL-ek

Az `applicationsets/` fájlokban a cluster URL-eket (`https://*.eks.example.com`) a valós EKS endpoint-okra kell cserélni, és az ArgoCD-ben regisztrálni kell őket (`argocd cluster add`).
