file-api: gunicorn --bind=0.0.0.0:8000 --workers=4 --forwarded-allow-ips=* --timeout=3600 'cbng_trainer.api:create_app()'
cbng-trainer: ./deployment/entrypoint.sh
