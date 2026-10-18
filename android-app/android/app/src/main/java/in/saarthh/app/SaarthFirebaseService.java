package in.saarthh.app;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;

import com.google.firebase.messaging.FirebaseMessaging;
import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;

import org.json.JSONObject;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

public class SaarthFirebaseService extends FirebaseMessagingService {
    private static final String TAG = "SaarthFirebaseService";
    public static final String CHANNEL_ID = "saarth_alerts";
    public static final String CHANNEL_NAME = "SAARTH Alerts";
    public static final String PREFS_NAME = "saarth_app_prefs";
    public static final String KEY_FCM_TOKEN = "fcm_token";
    public static final String KEY_AUTH_TOKEN = "auth_token";
    private static final String API_BASE_URL = "https://api.saarthh.in";

    private static final AtomicInteger NOTIFICATION_ID_GENERATOR = new AtomicInteger(100);

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel(this);
    }

    public static void createNotificationChannel(Context context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                CHANNEL_NAME,
                NotificationManager.IMPORTANCE_HIGH
            );
            channel.setDescription("Critical budget notifications, alerts, and transaction updates");
            channel.enableVibration(true);
            NotificationManager manager = context.getSystemService(NotificationManager.class);
            if (manager != null) {
                manager.createNotificationChannel(channel);
            }
        }
    }

    @Override
    public void onMessageReceived(@NonNull RemoteMessage remoteMessage) {
        super.onMessageReceived(remoteMessage);
        Log.d(TAG, "From: " + remoteMessage.getFrom());

        String title = "SAARTH Alert";
        String body = "";
        String url = "/";

        Map<String, String> data = remoteMessage.getData();
        if (data != null && !data.isEmpty()) {
            if (data.containsKey("title") && data.get("title") != null) {
                title = data.get("title");
            }
            if (data.containsKey("body") && data.get("body") != null) {
                body = data.get("body");
            }
            if (data.containsKey("url") && data.get("url") != null) {
                url = data.get("url");
            }
        }

        if (remoteMessage.getNotification() != null) {
            if (remoteMessage.getNotification().getTitle() != null) {
                title = remoteMessage.getNotification().getTitle();
            }
            if (remoteMessage.getNotification().getBody() != null) {
                body = remoteMessage.getNotification().getBody();
            }
        }

        if (body != null && !body.isEmpty()) {
            showNotification(title, body, url);
        }
    }

    private void showNotification(String title, String body, String url) {
        createNotificationChannel(this);

        Intent intent = new Intent(this, MainActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        intent.putExtra("target_url", url);

        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }

        PendingIntent pendingIntent = PendingIntent.getActivity(
            this,
            NOTIFICATION_ID_GENERATOR.incrementAndGet(),
            intent,
            flags
        );

        NotificationCompat.Builder builder = new NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(new NotificationCompat.BigTextStyle().bigText(body))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent);

        NotificationManagerCompat notificationManager = NotificationManagerCompat.from(this);
        try {
            notificationManager.notify(NOTIFICATION_ID_GENERATOR.incrementAndGet(), builder.build());
        } catch (SecurityException se) {
            Log.w(TAG, "Missing notification permission to display notification: " + se.getMessage());
        } catch (Exception e) {
            Log.e(TAG, "Failed to display notification", e);
        }
    }

    @Override
    public void onNewToken(@NonNull String token) {
        super.onNewToken(token);
        Log.d(TAG, "Refreshed FCM token: " + token);

        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        prefs.edit().putString(KEY_FCM_TOKEN, token).apply();

        String authToken = prefs.getString(KEY_AUTH_TOKEN, null);
        if (authToken != null && !authToken.trim().isEmpty()) {
            sendTokenToServer(token, authToken);
        } else {
            Log.d(TAG, "User not yet authenticated. Stored FCM token for post-login sync.");
        }
    }

    public static void syncTokenWithServer(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        String authToken = prefs.getString(KEY_AUTH_TOKEN, null);
        if (authToken == null || authToken.trim().isEmpty()) {
            Log.d(TAG, "syncTokenWithServer: auth token is missing, skipping sync.");
            return;
        }

        String fcmToken = prefs.getString(KEY_FCM_TOKEN, null);
        if (fcmToken != null && !fcmToken.trim().isEmpty()) {
            sendTokenToServer(fcmToken, authToken);
        } else {
            FirebaseMessaging.getInstance().getToken().addOnCompleteListener(task -> {
                if (task.isSuccessful() && task.getResult() != null) {
                    String token = task.getResult();
                    prefs.edit().putString(KEY_FCM_TOKEN, token).apply();
                    sendTokenToServer(token, authToken);
                } else {
                    Log.w(TAG, "Failed to retrieve FCM registration token", task.getException());
                }
            });
        }
    }

    public static void sendTokenToServer(String fcmToken, String authToken) {
        new Thread(() -> {
            HttpURLConnection conn = null;
            try {
                URL url = new URL(API_BASE_URL + "/api/push/fcm-token");
                conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8");
                conn.setRequestProperty("Authorization", "Bearer " + authToken);
                conn.setConnectTimeout(10000);
                conn.setReadTimeout(10000);
                conn.setDoOutput(true);

                JSONObject payload = new JSONObject();
                payload.put("token", fcmToken);
                payload.put("platform", "android");

                byte[] postData = payload.toString().getBytes(StandardCharsets.UTF_8);
                try (OutputStream os = conn.getOutputStream()) {
                    os.write(postData);
                    os.flush();
                }

                int responseCode = conn.getResponseCode();
                Log.d(TAG, "Sent FCM token to server, HTTP response: " + responseCode);
            } catch (Exception e) {
                Log.e(TAG, "Failed to send FCM token to backend", e);
            } finally {
                if (conn != null) {
                    conn.disconnect();
                }
            }
        }).start();
    }
}
