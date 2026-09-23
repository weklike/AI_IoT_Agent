FROM charge-ops-frontend:test-94f8cb9ab56df832
RUN rm -rf /usr/share/nginx/html/assets /usr/share/nginx/html/index.html
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend/dist/ /usr/share/nginx/html/
