# Przeglądarka bazy SQLite - w docker-compose.yml przypięta do 127.0.0.1, więc
# nie wychodzi poza maszynę. W Helmie ten sam sidecar jest domyślnie wyłączony
# (values.yaml -> dbWeb.enabled), bo w klastrze nasłuchiwałby na IP poda bez
# żadnego uwierzytelniania.
#
# Przypięte po digeście, nie po tagu: coleifer/sqlite-web publikuje wyłącznie
# "latest" (brak tagów wersji). Digest odpowiada "latest" z 2025-03-02 i jest
# ten sam co w charts/ogrodnik/values.yaml.
FROM coleifer/sqlite-web@sha256:1e5b86237968ed747554f951c6df2fc2fe4bf4ef070b8ca23d553d7f6c6426f7
