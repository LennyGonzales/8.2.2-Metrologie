# gonzales-lenny-prometheus-grafana

## Structure du projet

```text
README.md
kind-config.yaml
app/
  main.py
  requirements.txt
  Dockerfile
  .dockerignore
  generate-traffic.sh
manifests/
  00-namespaces.yaml
  01-prometheus-rbac.yaml
  02-prometheus-config.yaml
  03-prometheus-deployment-service.yaml
  04-alertmanager.yaml
  05-node-exporter.yaml
  06-kube-state-metrics.yaml
  07-grafana-dashboard.yaml
  08-grafana-deployment-service.yaml
  09-demo-app.yaml
grafana/
  dashboard.json
```

## Procédure de déploiement

### 1. Construire l'image de l'application

```bash
cd app
docker build -t gonzales-lenny-prometheus-grafana-app:1.0.0 .
```

### 2. Création du cluster

```bash
kind create cluster --config kind-config.yaml
```

### 3. Importation de l'image docker de l'api demo

```bash
kind load docker-image gonzales-lenny-prometheus-grafana-app:1.0.0 --name gonzales-lenny-prometheus-grafana
```

### 3. Execution des services

```bash
kubectl apply -f manifests/
```

Pour visualiser leur création :
```bash
kubectl -n monitoring wait --for=condition=ready pod -l app=prometheus --timeout=120s
kubectl -n monitoring wait --for=condition=ready pod -l app=alertmanager --timeout=120s
kubectl -n monitoring wait --for=condition=ready pod -l app=grafana --timeout=120s
kubectl -n demo wait --for=condition=ready pod -l app=demo-api --timeout=120s

kubectl -n monitoring get pods
kubectl -n demo get pods
```

## Accès aux services

**Demo api** : http://localhost:8080/ok
**Prometheus** : http://localhost:9090/targets
**Grafana** : http://localhost:3000
**Alertmanager** : http://localhost:9093

## Génération de traffic

```bash
./app/generate-traffic.sh http://localhost:8080
```

## Procédure de suppression

```bash
kind delete cluster --name gonzales-lenny-prometheus-grafana
```

## Instrumentation de l'application

- **`prometheus-fastapi-instrumentator`** : métriques HTTP automatiques (`http_requests_total`) avec regroupement par famille de statut (`2xx`, `4xx`, `5xx`), exposées sur `/metrics`.
- **Compteur custom `app_slow_requests_total{endpoint}`** : incrémenté sur `/slow` (réponse > 2s).
- **Découverte Prometheus** : annotations pod `prometheus.io/scrape`, `port` et `path` dans `09-demo-app.yaml`.

Endpoints de test : `/ok`, `/bad-request` (400), `/not-found` (404), `/error` (500), `/crash` (503), `/slow`.

## Requêtes PromQL

### Dashboard Grafana

| Panel | Requête PromQL |
|---|---|
| A — 5xx sur 5 min | `sum(increase(http_requests_total{job="demo-api",status="5xx"}[5m]))` |
| B — 4xx et 5xx | `sum by (status) (increase(http_requests_total{job="demo-api",status=~"4xx\|5xx"}[5m]))` |
| C — évolution par famille | `sum(rate(http_requests_total{job="demo-api",status="2xx"}[1m]))` (+ 4xx, 5xx) |
| D — camembert | `sum by (status) (increase(http_requests_total{job="demo-api"}[5m]))` |
| E — métrique custom | `sum by (endpoint) (rate(app_slow_requests_total{job="demo-api"}[5m]))` |

### Alertes

| Alerte | Expression | Durée |
|---|---|---|
| 1 — Composant indisponible | `up{job=~"prometheus\|alertmanager\|grafana\|node-exporter\|kube-state-metrics\|demo-api"} == 0` ou `kube_deployment_status_replicas_available{namespace=~"monitoring\|demo",deployment=~"prometheus\|alertmanager\|grafana\|kube-state-metrics\|demo-api"} < 1` | 1m (criticité élevée) |
| 2 — Trop d'erreurs 5xx | `sum(increase(http_requests_total{job="demo-api",status="5xx"}[5m])) > 20` | 1m (criticité élevée) |
| 3 — Alertmanager indisponible (K8s) | `kube_deployment_status_replicas_available{namespace="monitoring",deployment="alertmanager"} < 1` | 2m (l'état K8s peut mettre quelques secondes à se stabiliser après un restart) |
| 4 — Requêtes lentes | `sum(rate(app_slow_requests_total{job="demo-api"}[5m])) > 0.1` | 2m (car un pic très court ne justifie pas une notification) |

| Alerte | Méthode | Vérification |
|---|---|---|
| 5xx + requêtes lentes | `./app/generate-traffic.sh http://localhost:8080` | `HighHttp5xxErrors`, `HighSlowRequestRate` (`Firing` après 1 min) |
| Composant indisponible | `kubectl -n demo scale deployment demo-api --replicas=0` (puis `--replicas=1`) | `ComponentDown` |
| Alertmanager indisponible | `kubectl -n monitoring scale deployment alertmanager --replicas=0` (puis `--replicas=1`) | `AlertmanagerDeploymentUnavailable` |

## Hypothèses et limites

- Utilisation d'un environnement **kind** local (stockage Prometheus/AlertManager éphémère (`emptyDir`)), et les dashboards Grafana sont montés via `hostPath` depuis `./grafana`.
- L'Alertmanager configuré avec un receiver `default` minimal (pas de notification email/Slack). Cela oblige donc à regarder en permanence le dashboard au lieu d'être avertit quand quelque chose ne va pas.
- Latence de détection : Le scrape et l'évaluation sont effectués toutes les **15s**, puis délai `for` de **1 à 2 min** avant `Firing`. Une panne inférieur à 1 min ou un pic de 5xx très court peut ne pas déclencher d'alerte.

