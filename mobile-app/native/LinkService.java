package dev.kiyan.orion;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.media.AudioAttributes;
import android.media.AudioManager;
import android.media.MediaPlayer;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.VibrationEffect;
import android.os.Vibrator;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Keeps the phone linked to the PC even when the ORION app is closed.
 * Every ~20 seconds it asks the PC "anything urgent?" — if ORION wants to CALL, the phone rings with a
 * full-screen incoming call; if you asked ORION to FIND your phone, it rings loudly even on silent.
 */
public class LinkService extends Service {
    public static final String PREFS = "orion_link";
    public static final String STOP_RING = "dev.kiyan.orion.STOP_RING";
    private static final String CH_LINK = "orion_link", CH_CALL = "orion_calls", CH_RING = "orion_ring";
    private Handler handler;
    private HandlerThread thread;
    private MediaPlayer player;
    private int savedVolume = -1;

    public static void start(Context c) {
        Intent i = new Intent(c, LinkService.class);
        if (Build.VERSION.SDK_INT >= 26) c.startForegroundService(i); else c.startService(i);
    }

    @Override
    public IBinder onBind(Intent intent) { return null; }

    @Override
    public void onCreate() {
        super.onCreate();
        channels();
        startAsForeground();
        thread = new HandlerThread("orion-link");
        thread.start();
        handler = new Handler(thread.getLooper());
        handler.post(poll);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && STOP_RING.equals(intent.getAction())) stopRing();
        return START_STICKY;
    }

    private final Runnable poll = new Runnable() {
        @Override
        public void run() {
            try { check(); } catch (Exception ignored) { }
            handler.postDelayed(this, 20000);
        }
    };

    private void check() throws Exception {
        SharedPreferences sp = getSharedPreferences(PREFS, MODE_PRIVATE);
        String addr = sp.getString("addr", ""), pin = sp.getString("pin", "");
        if (addr.isEmpty()) return;
        if (addr.endsWith("/")) addr = addr.substring(0, addr.length() - 1);
        HttpURLConnection c = (HttpURLConnection) new URL(addr + "/api/wake").openConnection();
        c.setConnectTimeout(6000);
        c.setReadTimeout(8000);
        c.setRequestProperty("X-PIN", pin);
        if (c.getResponseCode() != 200) { c.disconnect(); return; }
        StringBuilder sb = new StringBuilder();
        BufferedReader r = new BufferedReader(new InputStreamReader(c.getInputStream(), "UTF-8"));
        String line;
        while ((line = r.readLine()) != null) sb.append(line);
        r.close();
        c.disconnect();
        JSONArray acts = new JSONObject(sb.toString()).optJSONArray("actions");
        if (acts == null) return;
        for (int k = 0; k < acts.length(); k++) {
            JSONObject a = acts.getJSONObject(k);
            String kind = a.optString("kind");
            if ("call".equals(kind)) incomingCall(a.optString("reason", ""));
            else if ("ring".equals(kind)) ring();
        }
    }

    private PendingIntent openApp(String action, String reason, int code) {
        Intent i = new Intent(this, MainActivity.class);
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        i.putExtra("orion_action", action);
        i.putExtra("orion_reason", reason);
        return PendingIntent.getActivity(this, code, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    private Notification.Builder builder(String ch) {
        return Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, ch) : new Notification.Builder(this);
    }

    private void incomingCall(String reason) {
        PendingIntent answer = openApp("call", reason, 11);
        Notification n = builder(CH_CALL)
                .setSmallIcon(android.R.drawable.sym_call_incoming)
                .setContentTitle("ORION is calling")
                .setContentText(reason.isEmpty() ? "Tap to answer" : reason)
                .setCategory(Notification.CATEGORY_CALL)
                .setPriority(Notification.PRIORITY_MAX)
                .setFullScreenIntent(answer, true)
                .setContentIntent(answer)
                .setAutoCancel(true)
                .setTimeoutAfter(45000)
                .addAction(new Notification.Action.Builder(null, "Answer", answer).build())
                .build();
        ((NotificationManager) getSystemService(NOTIFICATION_SERVICE)).notify(21, n);
        vibrate(new long[]{0, 800, 600, 800, 600, 800});
    }

    private void ring() {
        try {
            stopRing();
            AudioManager am = (AudioManager) getSystemService(AUDIO_SERVICE);
            savedVolume = am.getStreamVolume(AudioManager.STREAM_ALARM);
            am.setStreamVolume(AudioManager.STREAM_ALARM, am.getStreamMaxVolume(AudioManager.STREAM_ALARM), 0);
            Uri tone = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM);
            if (tone == null) tone = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE);
            player = new MediaPlayer();
            player.setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build());
            player.setDataSource(this, tone);
            player.setLooping(true);
            player.prepare();
            player.start();
            handler.postDelayed(this::stopRing, 60000);
        } catch (Exception ignored) { }
        Intent stop = new Intent(this, LinkService.class).setAction(STOP_RING);
        PendingIntent stopPi = Build.VERSION.SDK_INT >= 26
                ? PendingIntent.getForegroundService(this, 13, stop, PendingIntent.FLAG_IMMUTABLE)
                : PendingIntent.getService(this, 13, stop, PendingIntent.FLAG_IMMUTABLE);
        PendingIntent open = openApp("ring", "", 12);
        Notification n = builder(CH_RING)
                .setSmallIcon(android.R.drawable.ic_lock_silent_mode_off)
                .setContentTitle("📢 Found it!")
                .setContentText("ORION is ringing your phone — tap to stop")
                .setCategory(Notification.CATEGORY_ALARM)
                .setPriority(Notification.PRIORITY_MAX)
                .setFullScreenIntent(open, true)
                .setContentIntent(stopPi)
                .setDeleteIntent(stopPi)
                .setAutoCancel(true)
                .addAction(new Notification.Action.Builder(null, "Stop", stopPi).build())
                .build();
        ((NotificationManager) getSystemService(NOTIFICATION_SERVICE)).notify(22, n);
        vibrate(new long[]{0, 1000, 400, 1000, 400, 1000, 400, 1000});
    }

    private void stopRing() {
        try {
            if (player != null) { player.stop(); player.release(); }
        } catch (Exception ignored) { }
        player = null;
        if (savedVolume >= 0) {
            try {
                ((AudioManager) getSystemService(AUDIO_SERVICE)).setStreamVolume(AudioManager.STREAM_ALARM, savedVolume, 0);
            } catch (Exception ignored) { }
            savedVolume = -1;
        }
        ((NotificationManager) getSystemService(NOTIFICATION_SERVICE)).cancel(22);
    }

    private void vibrate(long[] pattern) {
        try {
            Vibrator v = (Vibrator) getSystemService(VIBRATOR_SERVICE);
            if (Build.VERSION.SDK_INT >= 26) v.vibrate(VibrationEffect.createWaveform(pattern, -1));
            else v.vibrate(pattern, -1);
        } catch (Exception ignored) { }
    }

    private void channels() {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        nm.createNotificationChannel(new NotificationChannel(CH_LINK, "ORION link (background)", NotificationManager.IMPORTANCE_MIN));
        NotificationChannel call = new NotificationChannel(CH_CALL, "ORION calls", NotificationManager.IMPORTANCE_HIGH);
        call.setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE),
                new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION_RINGTONE).build());
        call.enableVibration(true);
        nm.createNotificationChannel(call);
        NotificationChannel ring = new NotificationChannel(CH_RING, "Find my phone", NotificationManager.IMPORTANCE_HIGH);
        ring.setSound(null, null);
        nm.createNotificationChannel(ring);
    }

    private void startAsForeground() {
        Notification n = builder(CH_LINK).setContentTitle("ORION is linked to your PC")
                .setContentText("Calls and find-my-phone work even with the app closed")
                .setSmallIcon(android.R.drawable.stat_notify_sync_noanim).setOngoing(true)
                .setContentIntent(openApp("", "", 10)).build();
        if (Build.VERSION.SDK_INT >= 34) startForeground(8, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        else startForeground(8, n);
    }

    @Override
    public void onDestroy() {
        stopRing();
        if (thread != null) thread.quitSafely();
        super.onDestroy();
    }
}
