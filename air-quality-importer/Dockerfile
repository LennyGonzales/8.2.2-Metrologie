FROM docker.elastic.co/logstash/logstash:8.19.16

RUN rm -f /usr/share/logstash/pipeline/logstash.conf

COPY pipeline/logstash.conf /usr/share/logstash/pipeline/logstash.conf

ENV XPACK_MONITORING_ENABLED=false
