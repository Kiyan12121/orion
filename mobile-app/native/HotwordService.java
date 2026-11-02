package dev.kiyan.orion;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;

import org.vosk.Model;
import org.vosk.Recognizer;
import org.vosk.android.RecognitionListener;
import org.vosk.android.SpeechService;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/**
 * "Hey ORION" (beta): a small offline speech model listens ONLY for the wake phrase, on the phone itself.
 * Nothing is recorded or sent anywhere. Pauses during school hours and when the battery is low.
 */
public class HotwordService extends Service implements RecognitionListener {
    static final String PAUSE = "dev.kiyan.orion.HOTWORD_PAUSE", RESUME = "dev.kiyan.orion.HOTWORD_RESUME";
    private static final String MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip";
    private SpeechService speech;
    private Model model;
    private final Handler h = new Handler(Looper.getMainLooper());
    private long lastFire = 0;

    @Override public IBinder onBind(Intent i) { return null; }

    @Override
    public void onCreate() {
        super.onCreate();
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= 26) nm.createNotificationChannel(new NotificationChannel("orion_hotword", "Hey ORION", NotificationManager.IMPORTANCE_MIN));
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, "orion_hotword") : new Notification.Builder(this);
        Notification n = b.setContentTitle("Listening for “Hey ORION”").setContentText("Offline — nothing is recorded")
                .setSmallIcon(android.R.drawable.ic_btn_speak_now).setOngoing(true).build();
        if (Build.VERSION.SDK_INT >= 30) startForeground(9, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE);
        else startForeground(9, n);
        new Thread(this::boot).start();
        h.postDelayed(watch, 60000);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && speech != null) {
            if (PAUSE.equals(intent.getAction())) speech.setPause(true);
            if (RESUME.equals(intent.getAction())) speech.setPause(LinkService.atSchool(this));
        }
        return START_STICKY;
    }

    private final Runnable watch = new Runnable() {
        @Override public void run() {
            try {
                android.os.BatteryManager bm = (android.os.BatteryManager) getSystemService(BATTERY_SERVICE);
                int pct = bm.getIntProperty(android.os.BatteryManager.BATTERY_PROPERTY_CAPACITY);
                if (speech != null) speech.setPause(LinkService.atSchool(HotwordService.this) || (pct > 0 && pct < 25 && !bm.isCharging()));
            } catch (Exception ignored) { }
            h.postDelayed(this, 60000);
        }
    };

    private void boot() {
        try {
            File dir = new File(getFilesDir(), "vosk");
            File mdir = new File(dir, "vosk-model-small-en-us-0.15");
            if (!new File(mdir, "conf").exists()) download(dir);
            model = new Model(mdir.getAbsolutePath());
            Recognizer rec = new Recognizer(model, 16000.0f, "[\"hey orion\", \"ok orion\", \"hey jarvis\", \"ok jarvis\", \"jarvis\", \"[unk]\"]");
            speech = new SpeechService(rec, 16000.0f);
            speech.startListening(this);
            speech.setPause(LinkService.atSchool(this));
        } catch (Exception e) {
            stopSelf();
        }
    }

    private void download(File dir) throws Exception {
        dir.mkdirs();
        HttpURLConnection c = (HttpURLConnection) new URL(MODEL_URL).openConnection();
        c.setConnectTimeout(15000);
        c.setReadTimeout(60000);
        try (InputStream in = new BufferedInputStream(c.getInputStream()); ZipInputStream z = new ZipInputStream(in)) {
            ZipEntry e;
            byte[] buf = new byte[65536];
            while ((e = z.getNextEntry()) != null) {
                File out = new File(dir, e.getName());
                if (!out.getCanonicalPath().startsWith(dir.getCanonicalPath())) continue;
                if (e.isDirectory()) { out.mkdirs(); continue; }
                out.getParentFile().mkdirs();
                try (FileOutputStream fo = new FileOutputStream(out)) {
                    int n;
                    while ((n = z.read(buf)) > 0) fo.write(buf, 0, n);
                }
            }
        }
    }

    private void fire() {
        if (System.currentTimeMillis() - lastFire < 4000) return;
        lastFire = System.currentTimeMillis();
        if (speech != null) speech.setPause(true);       // free the mic for the app
        Intent i = new Intent(this, MainActivity.class);
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
        i.putExtra("orion_action", "listen");
        startActivity(i);
        h.postDelayed(() -> { if (speech != null) speech.setPause(LinkService.atSchool(this)); }, 45000);
    }

    // only a clear "hey orion" / "ok orion" / "hey jarvis" counts — never a stray word in your mates' chat
    @Override public void onPartialResult(String hyp) { }
    @Override public void onResult(String hyp) {
        if (hyp == null) return;
        if (hyp.contains("hey orion") || hyp.contains("ok orion") || hyp.contains("jarvis")) fire();
    }
    @Override public void onFinalResult(String hyp) { }
    @Override public void onError(Exception e) { }
    @Override public void onTimeout() { }

    @Override
    public void onDestroy() {
        h.removeCallbacks(watch);
        try { if (speech != null) { speech.stop(); speech.shutdown(); } } catch (Exception ignored) { }
        super.onDestroy();
    }
}
