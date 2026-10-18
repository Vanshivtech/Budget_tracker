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
    private static final String KEY_SMS_DENIED = "sms_permission_denied";

    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(in.saarthh.app.plugins.SmsReaderPlugin.class);
        super.onCreate(savedInstanceState);

        checkFirstLaunchPermissions();
    }

    private void checkFirstLaunchPermissions() {
        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        boolean alreadyRequested = prefs.getBoolean(KEY_PERMISSIONS_REQUESTED, false);
        if (!alreadyRequested) {
            showPermissionExplanationDialog();
        } else {
            // If already requested previously and SMS permission is still denied, notify webview
            boolean smsPermissionMissing = ContextCompat.checkSelfPermission(this, Manifest.permission.READ_SMS) != PackageManager.PERMISSION_GRANTED
                || ContextCompat.checkSelfPermission(this, Manifest.permission.RECEIVE_SMS) != PackageManager.PERMISSION_GRANTED;
            if (smsPermissionMissing && prefs.getBoolean(KEY_SMS_DENIED, false)) {
                notifyWebviewPermissionDenied();
            }
        }
    }

    private void showPermissionExplanationDialog() {
        new AlertDialog.Builder(this)
            .setTitle("Permissions Required")
            .setMessage("SAARTH needs SMS access to auto-import your bank transactions.\n\nNotification permission lets us alert you about budget limits.")
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
                    markPermissionsRequested(true);
                    notifyWebviewPermissionDenied();
                }
            })
            .show();
    }

    private void requestAppPermissions() {
        List<String> permissions = new ArrayList<>();
        permissions.add(Manifest.permission.RECEIVE_SMS);
        permissions.add(Manifest.permission.READ_SMS);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissions.add(Manifest.permission.POST_NOTIFICATIONS);
        }

        List<String> needed = new ArrayList<>();
        for (String perm : permissions) {
            if (ContextCompat.checkSelfPermission(this, perm) != PackageManager.PERMISSION_GRANTED) {
                needed.add(perm);
            }
        }

        if (!needed.isEmpty()) {
            ActivityCompat.requestPermissions(this, needed.toArray(new String[0]), PERMISSION_REQUEST_CODE);
        } else {
            markPermissionsRequested(false);
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions, @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == PERMISSION_REQUEST_CODE) {
            boolean smsDenied = false;
            for (int i = 0; i < permissions.length; i++) {
                if (Manifest.permission.RECEIVE_SMS.equals(permissions[i]) || Manifest.permission.READ_SMS.equals(permissions[i])) {
                    if (grantResults[i] != PackageManager.PERMISSION_GRANTED) {
                        smsDenied = true;
                    }
                }
            }
            markPermissionsRequested(smsDenied);
            if (smsDenied) {
                notifyWebviewPermissionDenied();
            }
        }
    }

    private void markPermissionsRequested(boolean smsDenied) {
        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        prefs.edit()
            .putBoolean(KEY_PERMISSIONS_REQUESTED, true)
            .putBoolean(KEY_SMS_DENIED, smsDenied)
            .apply();
    }

    private void notifyWebviewPermissionDenied() {
        if (getBridge() != null && getBridge().getWebView() != null) {
            getBridge().getWebView().post(new Runnable() {
                @Override
                public void run() {
                    getBridge().getWebView().evaluateJavascript(
                        "if (typeof window.onSmsPermissionDenied === 'function') { window.onSmsPermissionDenied(); }",
                        null
                    );
                }
            });
        }
    }
}
