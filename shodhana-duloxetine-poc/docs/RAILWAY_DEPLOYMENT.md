# Railway Deployment

This POC can run on Railway as a Python web service.

## Service Settings

If deploying from the parent repository, set:

```text
Root Directory: /shodhana-duloxetine-poc
```

Railway/Nixpacks will detect Python because this folder has `requirements.txt`.

The `Procfile` start command is:

```text
web: python app.py
```

Railway provides the `PORT` environment variable automatically. The app listens on `0.0.0.0` and uses that `PORT`.

## Persistent SQLite Data

Create a Railway volume and mount it at:

```text
/app/persistent-data
```

Add this Railway variable:

```text
SHODHANA_DATA_DIR=/app/persistent-data
```

This keeps the SQLite database and uploaded files persistent across redeploys.

Do not mount the volume at `/app/data` for this POC, because the repo also stores demo sample files under `data/samples`.

## Public URL

After the service deploys:

1. Open the service in Railway.
2. Go to `Settings`.
3. Open `Networking`.
4. Click `Generate Domain`.
5. Open the generated Railway URL.

## First Demo Steps

1. Open the Railway public URL.
2. Click `Import Sample File`.
3. Open `Cleaning Review`.
4. Click `Re-run Cleaning`.
5. Open `Dashboard`.
6. Open `Opportunities`.
7. Click `Generate Pitch`.

## Notes

- This is suitable for a controlled demo.
- Do not upload confidential production files until access protection is added.
- The current app uses SQLite. For production, migrate to PostgreSQL and add proper authentication.
