package in.saarthh.app.plugins;

import android.Manifest;
import android.content.BroadcastReceiver;
import android.content.ContentResolver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Telephony;
import android.telephony.SmsMessage;
import android.util.Log;

import androidx.core.content.ContextCompat;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

@CapacitorPlugin(
    name = "SmsReaderPlugin",
    permissions = {
        @Permission(
            alias = "sms",
            strings = {
                Manifest.permission.READ_SMS,
                Manifest.permission.RECEIVE_SMS
            }
        )
    }
)
public class SmsReaderPlugin extends Plugin {
    private static final String TAG = "SmsReaderPlugin";

    // Supported banking and payment SMS senders (case-insensitive substring/prefix matching)
    private static final Set<String> ALLOWED_SENDERS = new HashSet<>(Arrays.asList(
        "SBIINB", "HDFCBK", "ICICIB", "AXISBK", "KOTAKB",
        "PNBSMS", "BOIIND", "CANBNK", "UNIONB",
        "PAYTM", "PHONEPE", "GPAY"
    ));

    private BroadcastReceiver smsReceiver;
    private boolean isListening = false;

    private boolean isSenderAllowed(String sender) {
        if (sender == null || sender.trim().isEmpty()) {
            return false;
        }
        String cleanSender = sender.toUpperCase(Locale.ROOT).replaceAll("[^A-Z0-9]", "");
        for (String target : ALLOWED_SENDERS) {
            if (cleanSender.contains(target)) {
                return true;
            }
        }
        return false;
    }

    @PluginMethod
    public void startListening(PluginCall call) {
        if (getPermissionState("sms") != com.getcapacitor.PermissionState.GRANTED) {
            requestPermissionForAlias("sms", call, "smsPermissionCallback");
            return;
        }
        setupSmsReceiver(call);
    }

    @PermissionCallback
    private void smsPermissionCallback(PluginCall call) {
        if (getPermissionState("sms") == com.getcapacitor.PermissionState.GRANTED) {
            setupSmsReceiver(call);
        } else {
            Log.w(TAG, "SMS permissions denied by user.");
            JSObject ret = new JSObject();
            ret.put("status", "denied");
            call.resolve(ret);
        }
    }

    private synchronized void setupSmsReceiver(PluginCall call) {
        if (isListening && smsReceiver != null) {
            JSObject ret = new JSObject();
            ret.put("status", "listening");
            call.resolve(ret);
            return;
        }

        try {
            smsReceiver = new BroadcastReceiver() {
                @Override
                public void onReceive(Context context, Intent intent) {
                    if (intent == null || !Telephony.Sms.Intents.SMS_RECEIVED_ACTION.equals(intent.getAction())) {
                        return;
                    }

                    Bundle bundle = intent.getExtras();
                    if (bundle == null) return;

                    Object[] pdus = (Object[]) bundle.get("pdus");
                    if (pdus == null || pdus.length == 0) return;

                    String format = bundle.getString("format");
                    StringBuilder bodyBuilder = new StringBuilder();
                    String sender = null;
                    long timestamp = System.currentTimeMillis();

                    for (Object pdu : pdus) {
                        SmsMessage message;
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                            message = SmsMessage.createFromPdu((byte[]) pdu, format);
                        } else {
                            message = SmsMessage.createFromPdu((byte[]) pdu);
                        }

                        if (message != null) {
                            if (sender == null) {
                                sender = message.getDisplayOriginatingAddress();
                                timestamp = message.getTimestampMillis();
                            }
                            bodyBuilder.append(message.getMessageBody());
                        }
                    }

                    if (sender != null && isSenderAllowed(sender)) {
                        JSObject eventData = new JSObject();
                        eventData.put("sender", sender);
                        eventData.put("body", bodyBuilder.toString());
                        eventData.put("timestamp", timestamp);

                        notifyListeners("smsReceived", eventData);
                        Log.d(TAG, "Emitted smsReceived from bank sender: " + sender);
                    }
                }
            };

            IntentFilter filter = new IntentFilter(Telephony.Sms.Intents.SMS_RECEIVED_ACTION);
            filter.setPriority(IntentFilter.SYSTEM_HIGH_PRIORITY);

            getContext().registerReceiver(smsReceiver, filter);
            isListening = true;

            JSObject ret = new JSObject();
            ret.put("status", "listening");
            call.resolve(ret);
        } catch (Exception e) {
            Log.e(TAG, "Failed to register SMS receiver", e);
            call.reject("Failed to register SMS receiver: " + e.getMessage());
        }
    }

    @PluginMethod
    public synchronized void stopListening(PluginCall call) {
        if (isListening && smsReceiver != null) {
            try {
                getContext().unregisterReceiver(smsReceiver);
            } catch (Exception e) {
                Log.w(TAG, "Error unregistering receiver: " + e.getMessage());
            }
            smsReceiver = null;
            isListening = false;
        }
        JSObject ret = new JSObject();
        ret.put("status", "stopped");
        call.resolve(ret);
    }

    @PluginMethod
    public void backfillSms(PluginCall call) {
        if (getPermissionState("sms") != com.getcapacitor.PermissionState.GRANTED) {
            requestPermissionForAlias("sms", call, "backfillPermissionCallback");
            return;
        }
        executeBackfill(call);
    }

    @PermissionCallback
    private void backfillPermissionCallback(PluginCall call) {
        if (getPermissionState("sms") == com.getcapacitor.PermissionState.GRANTED) {
            executeBackfill(call);
        } else {
            JSObject ret = new JSObject();
            ret.put("status", "denied");
            ret.put("sms", new JSArray());
            call.resolve(ret);
        }
    }

    private void executeBackfill(PluginCall call) {
        int days = call.getInt("days", 90);
        long cutoffTime = System.currentTimeMillis() - ((long) days * 24 * 60 * 60 * 1000L);

        JSArray matches = new JSArray();
        ContentResolver resolver = getContext().getContentResolver();
        Uri inboxUri = Uri.parse("content://sms/inbox");

        String selection = "date >= ?";
        String[] selectionArgs = new String[]{ String.valueOf(cutoffTime) };
        String sortOrder = "date DESC LIMIT 500";

        Cursor cursor = null;
        try {
            cursor = resolver.query(inboxUri, new String[]{"address", "body", "date"}, selection, selectionArgs, sortOrder);
            if (cursor != null && cursor.moveToFirst()) {
                int addressIdx = cursor.getColumnIndex("address");
                int bodyIdx = cursor.getColumnIndex("body");
                int dateIdx = cursor.getColumnIndex("date");

                do {
                    String address = cursor.getString(addressIdx);
                    String body = cursor.getString(bodyIdx);
                    long date = cursor.getLong(dateIdx);

                    if (isSenderAllowed(address)) {
                        JSObject item = new JSObject();
                        item.put("sender", address);
                        item.put("body", body);
                        item.put("timestamp", date);
                        matches.put(item);
                    }
                } while (cursor.moveToNext());
            }

            JSObject ret = new JSObject();
            ret.put("status", "ok");
            ret.put("count", matches.length());
            ret.put("sms", matches);
            call.resolve(ret);
        } catch (Exception e) {
            Log.e(TAG, "Error backfilling SMS inbox", e);
            call.reject("Error backfilling SMS inbox: " + e.getMessage());
        } finally {
            if (cursor != null) {
                cursor.close();
            }
        }
    }

    @Override
    protected void handleOnDestroy() {
        if (isListening && smsReceiver != null) {
            try {
                getContext().unregisterReceiver(smsReceiver);
            } catch (Exception ignored) {}
            smsReceiver = null;
            isListening = false;
        }
        super.handleOnDestroy();
    }
}
