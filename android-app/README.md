# SAARTH Android App (Capacitor)

This folder contains the Capacitor project wrapper for **SAARTH**. It wraps the web application (`https://saarthh.in`) into an Android APK with native capabilities including bank SMS reading and auto-ingestion.

---

## Getting Started Locally

1. **Install dependencies:**
   ```bash
   cd android-app
   npm install
   ```

2. **Initialize Android Platform (first time only):**
   ```bash
   npx cap add android
   ```

3. **Sync web & native plugins:**
   Run this whenever frontend changes or plugin configuration is updated:
   ```bash
   npx cap sync
   ```

4. **Building Locally:**
   - To build and test locally, Android Studio with the Android SDK (API 34+) and Java 17 are required.
   - Open in Android Studio:
     ```bash
     npx cap open android
     ```
   - Build APK via Gradle:
     ```bash
     cd android && ./gradlew assembleDebug
     ```

> **Note:** You do not need Android Studio installed on your development machine if you use the automated CI/CD pipeline. The GitHub Actions workflow builds the APK in the cloud automatically.

---

## Automated CI/CD (GitHub Actions)

The `.github/workflows/build-android.yml` workflow automatically builds, packages, signs, and publishes the Android APK on every push to `main` and on version release tags (`v*`).

### Required GitHub Repository Secrets

Configure the following secrets in **GitHub Repository Settings → Secrets and variables → Actions**:

| Secret Name | Description | Example / Note |
| :--- | :--- | :--- |
| `KEYSTORE_BASE64` | Base64-encoded release `.keystore` or `.jks` file | `base64 -w 0 saarth.keystore` |
| `KEYSTORE_PASSWORD` | Password for the release keystore | Your keystore password |
| `KEY_ALIAS` | Key alias in keystore | `saarth` |
| `KEY_PASSWORD` | Private key password | Your key password |
| `SAARTH_ADMIN_TOKEN` | Admin JWT token for SAARTH API | Used by CI to call `POST https://api.saarthh.in/api/admin/app/version` |

---

## Architecture & SMS Auto-Ingest

- **Web Server Wrapper:** Configured in `capacitor.config.json` to point to `https://saarthh.in`.
- **Native SMS Plugin:** Located in `sms-plugin/`, listens for incoming SMS from Indian banking handles (`SBIINB`, `HDFCBK`, `ICICIB`, `AXISBK`, `KOTAKB`, `PNBSMS`, `BOIIND`, `CANBNK`, `UNIONB`, `PAYTM`, `PHONEPE`, `GPAY`) and emits events to `frontend/app.js`.
- **Backend Sync:** Transactions are securely dispatched to `POST https://api.saarthh.in/api/sms/ingest`.
