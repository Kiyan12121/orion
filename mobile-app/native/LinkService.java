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
        if (intent != null && WAKE_CALL.equals(intent.getAction())) incomingCall("__morning__");
        return START_STICKY;
    }

    private final Runnable poll = new Runnable() {
        @Override
        public void run() {
            try { check(); } catch (Exception ignored) { }
            try { rideTick(); } catch (Exception ignored) { }
            handler.postDelayed(this, interval());
        }
    };

    /** Battery-friendly: check often while you're using the phone, rarely when it's asleep or low on battery. */
    private long interval() {
        try {
            if (getSharedPreferences(PREFS, MODE_PRIVATE).getBoolean("riding", false)) return 15000;
            android.os.PowerManager pm = (android.os.PowerManager) getSystemService(POWER_SERVICE);
            android.os.BatteryManager bm = (android.os.BatteryManager) getSystemService(BATTERY_SERVICE);
            int pct = bm.getIntProperty(android.os.BatteryManager.BATTERY_PROPERTY_CAPACITY);
            if (pct > 0 && pct < 10) return 300000;
            if (pct > 0 && pct < 25) return 120000;
            return pm.isInteractive() ? 20000 : 60000;
        } catch (Exception e) { return 30000; }
    }

    /** School mode: silent between school start and end on school days (times sent by the app). */
    static boolean atSchool(Context c) {
        SharedPreferences sp = c.getSharedPreferences(PREFS, MODE_PRIVATE);
        if (sp.getBoolean("holiday", false)) return false;
        java.util.Calendar cal = java.util.Calendar.getInstance();
        int dow = cal.get(java.util.Calendar.DAY_OF_WEEK);
        if (dow == java.util.Calendar.SATURDAY || dow == java.util.Calendar.SUNDAY) return false;
        String now = String.format(java.util.Locale.UK, "%02d:%02d", cal.get(java.util.Calendar.HOUR_OF_DAY), cal.get(java.util.Calendar.MINUTE));
        return now.compareTo(sp.getString("school_start", "08:40")) >= 0 && now.compareTo(sp.getString("school_end", "15:10")) < 0;
    }

    // ---------------------------------------------------------------- ride timing (learns your school run)
    private void rideTick() {
        SharedPreferences sp = getSharedPreferences(PREFS, MODE_PRIVATE);
        if (!sp.getBoolean("riding", false)) return;
        android.location.Location loc = lastLocation(this);
        long started = sp.getLong("ride_start", 0);
        if (System.currentTimeMillis() - started > 90 * 60000L) { sp.edit().putBoolean("riding", false).apply(); return; }
        if (loc == null) return;
        float dLat = sp.getFloat("dest_lat", 0), dLon = sp.getFloat("dest_lon", 0);
        if (dLat == 0 && dLon == 0) return;
        float[] d = new float[1];
        android.location.Location.distanceBetween(loc.getLatitude(), loc.getLongitude(), dLat, dLon, d);
        String to = sp.getString("ride_to", "school");
        if (d[0] >= sp.getFloat("dest_radius", 120)) {             // Now Bar: live ETA while riding
            float d0 = sp.getFloat("ride_d0", 0);
            if (d0 <= 0 || d[0] > d0) { d0 = d[0]; sp.edit().putFloat("ride_d0", d0).apply(); }
            long eta = (long) (d[0] * 1.3f / 4.4f);
            java.util.Calendar at = java.util.Calendar.getInstance();
            at.add(java.util.Calendar.SECOND, (int) eta);
            String atS = String.format(java.util.Locale.UK, "%02d:%02d", at.get(java.util.Calendar.HOUR_OF_DAY), at.get(java.util.Calendar.MINUTE));
            long mins = Math.max(1, Math.round(eta / 60.0));
            String late = "";
            if ("school".equals(to)) {
                String start = sp.getString("school_start", "08:40");
                late = atS.compareTo(start) > 0 ? " · after " + start + "!" : " · before the bell";
            }
            NowBar.post(this, (to.equals("school") ? "School" : "Home") + " in " + mins + " min",
                    "Arrive " + atS + late + " · " + String.format(java.util.Locale.UK, "%.1f km to go", d[0] / 1000f),
                    mins + " min", (int) Math.max(0, d0 - d[0]), (int) Math.max(1, d0), "ride");
        }
        if (d[0] < sp.getFloat("dest_radius", 120)) {
            NowBar.clear(this);
            sp.edit().remove("ride_d0").apply();
            long secs = (System.currentTimeMillis() - started) / 1000;
            String rides = sp.getString("rides", "");
            rides += (rides.isEmpty() ? "" : ";") + sp.getString("ride_to", "school") + "," + (started / 1000) + "," + secs;
            if (rides.length() > 4000) rides = rides.substring(rides.indexOf(';') + 1);
            sp.edit().putBoolean("riding", false).putString("rides", rides).apply();
            Notification n = builder(CH_LINK).setSmallIcon(android.R.drawable.ic_menu_mylocation)
                    .setContentTitle("Arrived — " + (secs / 60) + "m " + (secs % 60) + "s")
                    .setContentText("Ride to " + sp.getString("ride_to", "school") + " logged.").setAutoCancel(true).build();
            ((NotificationManager) getSystemService(NOTIFICATION_SERVICE)).notify(31, n);
        }
    }

    @SuppressWarnings("MissingPermission")
    static android.location.Location lastLocation(Context c) {
        try {
            android.location.LocationManager lm = (android.location.LocationManager) c.getSystemService(LOCATION_SERVICE);
            android.location.Location best = null;
            for (String p : lm.getProviders(true)) {
                android.location.Location l = lm.getLastKnownLocation(p);
                if (l != null && (best == null || l.getTime() > best.getTime())) best = l;
            }
            if (c.getSharedPreferences(PREFS, MODE_PRIVATE).getBoolean("riding", false)) {
                for (String p : new String[]{"gps", "network"}) {
                    if (lm.isProviderEnabled(p)) lm.requestSingleUpdate(p, new android.location.LocationListener() {
                        @Override public void onLocationChanged(android.location.Location l) { }
                    }, android.os.Looper.getMainLooper());
                }
            }
            return best;
        } catch (Exception e) { return null; }
    }

    private void check() throws Exception {
        SharedPreferences sp = getSharedPreferences(PREFS, MODE_PRIVATE);
        String pin = sp.getString("pin", "");
        // both addresses (home Wi-Fi + Tailscale): try the one that worked last, then the others
        java.util.List<String> list = new java.util.ArrayList<>();
        String last = sp.getString("addr_ok", "");
        if (!last.isEmpty()) list.add(last);
        for (String a : (sp.getString("addrs", "") + "," + sp.getString("addr", "")).split(",")) {
            a = a.trim();
            if (a.endsWith("/")) a = a.substring(0, a.length() - 1);
            if (!a.isEmpty() && !list.contains(a)) list.add(a);
        }
        if (list.isEmpty()) return;
        HttpURLConnection c = null;
        for (String a : list) {
            try {
                HttpURLConnection t = (HttpURLConnection) new URL(a + "/api/wake").openConnection();
                t.setConnectTimeout(a.equals(last) ? 6000 : 4000);
                t.setReadTimeout(8000);
                t.setRequestProperty("X-PIN", pin);
                if (t.getResponseCode() == 200) { c = t; if (!a.equals(last)) sp.edit().putString("addr_ok", a).apply(); break; }
                t.disconnect();
            } catch (Exception ignored) { }
        }
        if (c == null) return;
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
            boolean school = atSchool(this);
            if ("call".equals(kind) && !school) incomingCall(a.optString("reason", ""));
            else if ("ring".equals(kind)) ring();          // find-my-phone always rings (you asked for it)
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

    static final String WAKE_CALL = "dev.kiyan.orion.WAKE_CALL";

    private void incomingCall(String reason) {
        PendingIntent answer = openApp("call", reason, 11);
        Notification n = builder(CH_CALL)
                .setSmallIcon(android.R.drawable.sym_call_incoming)
                .setContentTitle("ORION is calling")
                .setContentText(reason.isEmpty() ? "Tap to answer" : "__morning__".equals(reason) ? "Good morning — your wake-up call" : reason)
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
        if (Build.VERSION.SDK_INT >= 34) {
            int type = ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE;
            if (checkSelfPermission(android.Manifest.permission.ACCESS_FINE_LOCATION) == android.content.pm.PackageManager.PERMISSION_GRANTED
                    || checkSelfPermission(android.Manifest.permission.ACCESS_COARSE_LOCATION) == android.content.pm.PackageManager.PERMISSION_GRANTED)
                type |= ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION;
            try { startForeground(8, n, type); } catch (Exception e) { startForeground(8, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE); }
        } else startForeground(8, n);
    }

    @Override
    public void onDestroy() {
        stopRing();
        if (thread != null) thread.quitSafely();
        super.onDestroy();
    }
}
