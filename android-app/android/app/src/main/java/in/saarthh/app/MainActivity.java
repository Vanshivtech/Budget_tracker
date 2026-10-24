package in.saarthh.app;

import android.Manifest;
import android.app.AlertDialog;
import android.content.Context;
import android.content.DialogInterface;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import androidx.annotation.NonNull;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import com.getcapacitor.BridgeActivity;
import java.util.ArrayList;
import java.util.List;

public class MainActivity extends BridgeActivity {
    private static final int PERMISSION_REQUEST_CODE = 1001;
    private static final String PREFS_NAME = "saarth_app_prefs";
    private static final String KEY_PERMISSIONS_REQUESTED = "permissions_requested";

    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(in.saarthh.app.plugins.SmsReaderPlugin.class);
        super.onCreate(savedInstanceState);

        SaarthFirebaseService.createNotificationChannel(this);
        checkFirstLaunchPermissions();

        if (getBridge() != null && getBridge().getWebView() != null) {
            android.webkit.WebSettings settings = getBridge().getWebView().getSettings();
            String originalUa = settings.getUserAgentString();
            if (originalUa != null && !originalUa.contains("SAARTH_NATIVE_APP")) {
                settings.setUserAgentString(originalUa + " SAARTH_NATIVE_APP Capacitor");
            }
            getBridge().getWebView().addJavascriptInterface(new AndroidAuthInterface(), "AndroidAuth");
        }
        SaarthFirebaseService.syncTokenWithServer(this);
    }

    public class AndroidAuthInterface {
        @android.webkit.JavascriptInterface
        public void setAuthToken(String token) {
            if (token != null && !token.trim().isEmpty()) {
                getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                    .edit()
                    .putString(SaarthFirebaseService.KEY_AUTH_TOKEN, token.trim())
                    .apply();
                SaarthFirebaseService.syncTokenWithServer(MainActivity.this);
            }
        }

        @android.webkit.JavascriptInterface
        public void clearAuthToken() {
            getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                .edit()
                .remove(SaarthFirebaseService.KEY_AUTH_TOKEN)
                .apply();
        }

        @android.webkit.JavascriptInterface
        public String getAuthToken() {
            return getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                .getString(SaarthFirebaseService.KEY_AUTH_TOKEN, null);
        }

        @android.webkit.JavascriptInterface
        public boolean isNativeApp() {
            return true;
        }
    }

    private void checkFirstLaunchPermissions() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            SharedPreferences prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
            boolean alreadyRequested = prefs.getBoolean(KEY_PERMISSIONS_REQUESTED, false);
            if (!alreadyRequested && ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                showPermissionExplanationDialog();
            }
        }
    }

    private void showPermissionExplanationDialog() {
        new AlertDialog.Builder(this)
            .setTitle("Notifications Required")
            .setMessage("Notification permission allows SAARTH to alert you about budget limits, daily updates, and bill reminders.")
            .setCancelable(false)
            .setPositiveButton("Continue", new DialogInterface.OnClickListener() {
                @Override
                public void onClick(DialogInterface dialog, int which) {
                    requestAppPermissions();
                }
            })
            .setNegativeButton("Not Now", new DialogInterface.OnClickListener() {
                @Override
                public void onClick(DialogInterface dialog, int which) {
                    markPermissionsRequested();
                }
            })
            .show();
    }

    private void requestAppPermissions() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                ActivityCompat.requestPermissions(this, new String[]{Manifest.permission.POST_NOTIFICATIONS}, PERMISSION_REQUEST_CODE);
                return;
            }
        }
        markPermissionsRequested();
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions, @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == PERMISSION_REQUEST_CODE) {
            markPermissionsRequested();
        }
    }

    private void markPermissionsRequested() {
        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        prefs.edit()
            .putBoolean(KEY_PERMISSIONS_REQUESTED, true)
            .apply();
    }
}
