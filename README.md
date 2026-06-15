# gonzales-lenny-prometheus-grafana

TP Prometheus, Alertmanager et Grafana — stack de monitoring sur Kubernetes (kind) avec application FastAPI instrumentée.

## Prérequis

- Docker
- kubectl
- kind

## Structure du rendu

```text
gonzales-lenny-prometheus-grafana/
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

## Composants déployés

Les namespaces sont séparés :
- `monitoring` : stack d'observabilité
- `demo` : application instrumentée

## Procédure de déploiement

### 1. Construire l'image de l'application

| Propriété | Valeur |
|---|---|
| Nom logique | `gonzales-lenny-prometheus-grafana-app:1.0.0` |
| Tag Docker effectif | `gonzales-lenny-prometheus-grafana-app:1.0.0` |
| Port | `8000` |

> Docker impose des noms de dépôt en minuscules.

```bash
cd app
docker build -t gonzales-lenny-prometheus-grafana-app:1.0.0 .
```

### 2. Créer le cluster

```bash
kind create cluster --config kind-config.yaml
kind load docker-image gonzales-lenny-prometheus-grafana-app:1.0.0 --name gonzales-lenny-prometheus-grafana

kubectl apply -f manifests/

kubectl -n monitoring wait --for=condition=ready pod -l app=prometheus --timeout=120s
kubectl -n monitoring wait --for=condition=ready pod -l app=alertmanager --timeout=120s
kubectl -n monitoring wait --for=condition=ready pod -l app=grafana --timeout=120s
kubectl -n demo wait --for=condition=ready pod -l app=demo-api --timeout=120s

kubectl -n monitoring get pods
kubectl -n demo get pods
curl http://localhost:8080/ok

# Prometheus : http://localhost:9090/targets
# Grafana : http://localhost:3000
# Alertmanager : http://localhost:9093

./app/generate-traffic.sh http://localhost:8080

kind delete cluster --name gonzales-lenny-prometheus-grafana
```

## Endpoints de l'application

## Requêtes PromQL principales

### Dashboard Grafana

| Panel | Requête PromQL |
|---|---|
| A — 5xx sur 5 min | `sum(increase(http_requests_total{job="demo-api",status="5xx"}[5m]))` |
| B — 4xx et 5xx | `sum by (status) (increase(http_requests_total{job="demo-api",status=~"4xx\|5xx"}[5m]))` |
| C — évolution par famille | `sum(rate(http_requests_total{job="demo-api",status="2xx"}[1m]))` (+ 4xx, 5xx) |
| D — camembert | `sum by (status) (increase(http_requests_total{job="demo-api"}[5m]))` |
| E — métrique custom | `sum by (endpoint) (rate(app_slow_requests_total{job="demo-api"}[5m]))` |

### Alertes

| Alerte | Expression | `for` |
|---|---|---|
| 1 — Composant indisponible | `up{job=~"prometheus\|alertmanager\|grafana\|node-exporter\|kube-state-metrics\|demo-api"} == 0` | 1m |
| 2 — Trop d'erreurs 5xx | `sum(increase(http_requests_total{job="demo-api",status="5xx"}[5m])) > 5` | 1m |
| 3 — Alertmanager indisponible (K8s) | `kube_deployment_status_replicas_available{namespace="monitoring",deployment="alertmanager"} < 1` | 2m |
| 4 — Requêtes lentes | `sum(rate(app_slow_requests_total{job="demo-api"}[5m])) > 0.1` | 2m |

## Tests des alertes

### Alerte 5xx

```bash
./app/generate-traffic.sh http://localhost:8080
```

Vérifier dans Prometheus → Alerts → `HighHttp5xxErrors` (état `Firing` après 1 min).

### Alerte composant indisponible

```bash
kubectl -n demo scale deployment demo-api --replicas=0
# Attendre ~1 min, vérifier ComponentDown dans Prometheus et Alertmanager
kubectl -n demo scale deployment demo-api --replicas=1
```

### Alerte Alertmanager indisponible (Kubernetes)

```bash
kubectl -n monitoring scale deployment alertmanager --replicas=0
# Vérifier AlertmanagerDeploymentUnavailable (basée sur kube-state-metrics)
kubectl -n monitoring scale deployment alertmanager --replicas=1
```

### Alerte métrique custom

```bash
for i in $(seq 1 20); do curl -s -X POST -o /dev/null http://localhost:8080/trigger-slow; done
```

Vérifier `HighSlowRequestRate` dans Prometheus → Alerts.
