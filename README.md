# gonzales-lenny-prometheus-grafana-elk

Projet combinant le TP Prometheus/Grafana et le TP ELK Stack.

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
air-quality-importer/
  Dockerfile
  pipeline/logstash.conf
datasets/
  Air_Quality.log
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
  10-elasticsearch.yaml
  11-logstash.yaml
  12-kibana.yaml
  13-filebeat.yaml
  14-air-quality-import.yaml
grafana/
  dashboard.json
kibana/
  saved_objects.ndjson
```

## Déploiement et exploitation

### Images Docker

| Image | Tag | Usage |
| --- | --- | --- |
| `gonzales-lenny-prometheus-grafana-elk-app` | `1.0.0` | Application HTTP demo (métriques + logs JSON) |
| `gonzales-lenny-prometheus-grafana-elk-air-quality` | `1.0.0` | Import CSV Air Quality via Logstash |

### 1. Construire les images

```bash
cd app
docker build -t gonzales-lenny-prometheus-grafana-elk-app:1.0.0 .

cd ../air-quality-importer
docker build -t gonzales-lenny-prometheus-grafana-elk-air-quality:1.0.0 .
```

### 2. Créer le cluster

```bash
kind create cluster --config kind-config.yaml
```

### 3. Charger les images dans kind

```bash
kind load docker-image gonzales-lenny-prometheus-grafana-elk-app:1.0.0 --name gonzales-lenny-prometheus-grafana-elk
kind load docker-image gonzales-lenny-prometheus-grafana-elk-air-quality:1.0.0 --name gonzales-lenny-prometheus-grafana-elk
```

### 4. Déployer les services

```bash
kubectl apply -f manifests/
```

### 5. Attendre que les composants soient prêts

```bash
kubectl -n monitoring wait --for=condition=ready pod -l app=prometheus --timeout=120s
kubectl -n monitoring wait --for=condition=ready pod -l app=alertmanager --timeout=120s
kubectl -n monitoring wait --for=condition=ready pod -l app=grafana --timeout=120s
kubectl -n demo wait --for=condition=ready pod -l app=demo-api --timeout=120s
kubectl -n elastic wait --for=condition=ready pod -l app=elasticsearch --timeout=180s
kubectl -n elastic wait --for=condition=ready pod -l app=logstash --timeout=180s
kubectl -n elastic wait --for=condition=ready pod -l app=kibana --timeout=180s
kubectl -n elastic wait --for=condition=complete job/air-quality-importer --timeout=600s

kubectl -n monitoring get pods
kubectl -n demo get pods
kubectl -n elastic get pods
```


### Accès aux services

| Service | URL |
| --- | --- |
| Demo API | http://localhost:8080/ok |
| Prometheus | http://localhost:9090/targets |
| Grafana | http://localhost:3000 |
| Alertmanager | http://localhost:9093 |
| Kibana | http://localhost:5601 |

### Génération de trafic / logs

```bash
./app/generate-traffic.sh http://localhost:8080
```

Ce script alimente à la fois :

- les **métriques** Prometheus / Grafana ;
- les **logs** JSON consommés par Filebeat -> Logstash -> Elasticsearch -> Kibana.

Attendre 30 à 60 secondes après le trafic pour voir les logs dans Kibana.

---

# 1. Prometheus Grafana

## Composants concernés

Namespaces `monitoring` et `demo`. Manifests `01` à `09`, dashboard dans `grafana/`.

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

---

# 2. ELK

## Composants concernés

Namespace `elastic`. Manifests `10` à `14`, import CSV dans `air-quality-importer/`, objets Kibana exportables dans `kibana/saved_objects.ndjson`.

## Import Air Quality

L'import est déclenché automatiquement au déploiement par le Job `air-quality-importer` (`manifests/14-air-quality-import.yaml`).

Pipeline Logstash CSV : `air-quality-importer/pipeline/logstash.conf`. Le fichier `datasets/Air_Quality.log` est monté dans le pod via un `hostPath` kind (voir `kind-config.yaml`).

Index cible : `air-quality-*`

Relancer manuellement l'import :

```bash
kubectl -n elastic delete job air-quality-importer --ignore-not-found
kubectl apply -f manifests/14-air-quality-import.yaml
kubectl -n elastic wait --for=condition=complete job/air-quality-importer --timeout=600s
```

## Chaîne d'ingestion

```text
demo-api (stdout JSON)
    -> Filebeat (DaemonSet, namespace elastic)
    -> Logstash (pipeline app-logs)
    -> Elasticsearch
        index app-logs-*   (logs applicatifs)
        index stack-logs-* (autres logs collectés)
    -> Kibana
```

Les logs applicatifs sont distingués des logs techniques via :

- le champ `log_source: demo-api` ;
- l'index dédié `app-logs-*` (vs `stack-logs-*`).

## Structuration des logs applicatifs

Chaque requête HTTP produit une ligne JSON sur stdout.

Exemple :

```json
{
  "timestamp": "2026-06-16T10:00:00+00:00",
  "level": "INFO",
  "message": "HTTP request handled",
  "service": "demo-api",
  "request_id": "uuid",
  "route": "/ok",
  "method": "GET",
  "status_code": 200,
  "duration_ms": 3,
  "event": "http_request",
  "client_error": false
}
```

Champs utiles pour Kibana :

| Champ | Description |
| --- | --- |
| `@timestamp` | Horodatage (dérivé de `timestamp`) |
| `log_level` | INFO, WARNING, ERROR |
| `route` | Chemin HTTP |
| `status_code` | Code HTTP |
| `request_id` | Identifiant de corrélation |
| `event` | Type d'événement (`http_request`, `slow_response`, …) |
| `log_message` | Message lisible |

Aucune donnée sensible n'est loggée.

## Recherches Kibana principales

Import save_object.ndjson

| Recherche | KQL |
| --- | --- |
| Temporelle | Ajuster la time picker |
| Par niveau | `log_level: "ERROR"` |
| Par route | `route: "/error"` |
| Par request id | `request_id: "<valeur copiée depuis Discover>"` |
| Erreurs | `status_code >= 400` |

Data View : `air-quality-*`

| Recherche | KQL |
| --- | --- |
| Polluant + valeur + période | `pollutant: "Ozone (O3)" and data_value > 10 and @timestamp >= "2008-01-01" and @timestamp <= "2014-12-31"` |
| Filtre Bronx | `geo_place_name: "Bronx"` |

## Dashboards Kibana

### Dashboard développeur

Objectif : investiguer un incident technique.

Panels recommandés (Lens / Discover) :

- histogramme des erreurs (`status_code >= 400`) dans le temps ;
- top routes en erreur ;
- top messages (`log_message`) ;
- table des événements récents avec `request_id`, `route`, `status_code`.

### Dashboard support

Objectif : état fonctionnel sans jargon technique.

Panels recommandés :

- pourcentage de requêtes OK vs erreurs ;
- volume de trafic dans le temps ;
- indicateur « service indisponible » (`status_code >= 500`) ;
- résumé des requêtes lentes (`event: "slow_response"`).

### Dashboard Air Quality

Créer dans Kibana :

- Lens time-series : `Average(data_value)` sur `@timestamp`, split par `pollutant` ;
- heatmap ou table : `pollutant` × `time_period` ;
- contrôle Options list sur `geo_place_name` (test avec `Bronx`).

Exporter les dashboards finaux dans `kibana/` via **Stack Management -> Saved Objects -> Export**.

## Hypothèses et limites

- Utilisation d'un environnement **kind** local (stockage Elasticsearch éphémère (`emptyDir`)).
- Sécurité Elastic désactivée (`xpack.security.enabled=false`).
- Elasticsearch limité à 512 Mo de heap.
- Latence d'ingestion : 30 à 60 s entre génération de trafic et visibilité dans Kibana.
- L'import Air Quality (~16 000 lignes) peut prendre plusieurs minutes au premier lancement.

### Suppression du cluster

```bash
kind delete cluster --name gonzales-lenny-prometheus-grafana-elk
```