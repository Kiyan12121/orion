package dev.kiyan.orion;

import android.app.DownloadManager;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Environment;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.hardware.camera2.CameraManager;
import android.net.Uri;
import android.os.Build;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.provider.AlarmClock;
import android.provider.Settings;

import androidx.core.content.ContextCompat;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.util.List;
import java.util.Locale;

/** ORION's phone powers: alarms, timers, opening apps, torch, vibration and the floating bubble. */
@CapacitorPlugin(name = "OrionNative")
public class OrionNativePlugin extends Plugin {

    private void launch(Intent i) {
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        getContext().startActivity(i);
    }

    @PluginMethod
    public void setAlarm(PluginCall call) {
        try {
            Intent i = new Intent(AlarmClock.ACTION_SET_ALARM);
            i.putExtra(AlarmClock.EXTRA_HOUR, call.getInt("hour", 7));
            i.putExtra(AlarmClock.EXTRA_MINUTES, call.getInt("minute", 0));
            i.putExtra(AlarmClock.EXTRA_MESSAGE, call.getString("message", "ORION"));
            i.putExtra(AlarmClock.EXTRA_SKIP_UI, true);
            launch(i);
            call.resolve();
        } catch (Exception e) {
            call.reject("Couldn't set the alarm: " + e.getMessage());
        }
    }

    @PluginMethod
    public void setTimer(PluginCall call) {
        try {
            Intent i = new Intent(AlarmClock.ACTION_SET_TIMER);
            i.putExtra(AlarmClock.EXTRA_LENGTH, call.getInt("seconds", 60));
            i.putExtra(AlarmClock.EXTRA_MESSAGE, call.getString("message", "ORION"));
            i.putExtra(AlarmClock.EXTRA_SKIP_UI, true);
            launch(i);
            call.resolve();
        } catch (Exception e) {
            call.reject("Couldn't set the timer: " + e.getMessage());
        }
    }

    @PluginMethod
    public void showAlarms(PluginCall call) {
        try {
            launch(new Intent(AlarmClock.ACTION_SHOW_ALARMS));
            call.resolve();
        } catch (Exception e) {
            call.reject(e.getMessage());
        }
    }

    @PluginMethod
    public void openApp(PluginCall call) {
        String want = call.getString("name", "").toLowerCase(Locale.ROOT).trim();
        PackageManager pm = getContext().getPackageManager();
        Intent main = new Intent(Intent.ACTION_MAIN);
        main.addCategory(Intent.CATEGORY_LAUNCHER);
        List<ResolveInfo> apps = pm.queryIntentActivities(main, 0);
        ResolveInfo best = null;
        int bestScore = 0;
        for (ResolveInfo r : apps) {
            String label = String.valueOf(r.loadLabel(pm)).toLowerCase(Locale.ROOT);
            int score = label.equals(want) ? 3 : label.startsWith(want) ? 2 : label.contains(want) ? 1 : 0;
            if (score > bestScore) { bestScore = score; best = r; }
        }
        if (best == null) { call.reject("No app called '" + want + "' on this phone."); return; }
        Intent i = pm.getLaunchIntentForPackage(best.activityInfo.packageName);
        if (i == null) { call.reject("That app can't be opened."); return; }
        launch(i);
        JSObject ret = new JSObject();
        ret.put("opened", String.valueOf(best.loadLabel(pm)));
        call.resolve(ret);
    }

    @PluginMethod
    public void listApps(PluginCall call) {
        PackageManager pm = getContext().getPackageManager();
        Intent main = new Intent(Intent.ACTION_MAIN);
        main.addCategory(Intent.CATEGORY_LAUNCHER);
        JSArray arr = new JSArray();
        for (ResolveInfo r : pm.queryIntentActivities(main, 0)) arr.put(String.valueOf(r.loadLabel(pm)));
        JSObject ret = new JSObject();
        ret.put("apps", arr);
        call.resolve(ret);
    }

    @PluginMethod
    public void torch(PluginCall call) {
        try {
            CameraManager cm = (CameraManager) getContext().getSystemService(Context.CAMERA_SERVICE);
            cm.setTorchMode(cm.getCameraIdList()[0], call.getBoolean("on", true));
            call.resolve();
        } catch (Exception e) {
            call.reject("Torch unavailable: " + e.getMessage());
        }
    }

    @PluginMethod
    public void vibrate(PluginCall call) {
        try {
            Vibrator v = (Vibrator) getContext().getSystemService(Context.VIBRATOR_SERVICE);
            long ms = call.getInt("ms", 400);
            if (Build.VERSION.SDK_INT >= 26) v.vibrate(VibrationEffect.createOneShot(ms, VibrationEffect.DEFAULT_AMPLITUDE));
            else v.vibrate(ms);
            call.resolve();
        } catch (Exception e) {
            call.reject(e.getMessage());
        }
    }

    // ---------------- floating bubble overlay ----------------
    @PluginMethod
    public void canOverlay(PluginCall call) {
        JSObject ret = new JSObject();
        ret.put("granted", Build.VERSION.SDK_INT < 23 || Settings.canDrawOverlays(getContext()));
        call.resolve(ret);
    }

    @PluginMethod
    public void requestOverlay(PluginCall call) {
        try {
            launch(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:" + getContext().getPackageName())));
            call.resolve();
        } catch (Exception e) {
            call.reject(e.getMessage());
        }
    }

    @PluginMethod
    public void showBubble(PluginCall call) {
        if (Build.VERSION.SDK_INT >= 23 && !Settings.canDrawOverlays(getContext())) {
            call.reject("NEEDS_PERMISSION");
            return;
        }
        ContextCompat.startForegroundService(getContext(), new Intent(getContext(), BubbleService.class));
        call.resolve();
    }

    @PluginMethod
    public void hideBubble(PluginCall call) {
        getContext().stopService(new Intent(getContext(), BubbleService.class));
        call.resolve();
    }

    /** What the app was opened for (e.g. the bubble was tapped -> "call"). Read once, then cleared. */
    @PluginMethod
    public void consumeLaunchAction(PluginCall call) {
        JSObject ret = new JSObject();
        Intent i = getActivity() != null ? getActivity().getIntent() : null;
        String a = i != null ? i.getStringExtra("orion_action") : null;
        if (i != null) i.removeExtra("orion_action");
        String why = i != null ? i.getStringExtra("orion_reason") : null;
        if (i != null) i.removeExtra("orion_reason");
        ret.put("action", a == null ? "" : a);
        ret.put("reason", why == null ? "" : why);
        call.resolve(ret);
    }

    // ---------------------------------------------------------------- built-in Android voice (fallback)
    private android.speech.tts.TextToSpeech tts;
    private boolean ttsReady = false;

    private void ensureTts(Runnable then) {
        if (tts != null && ttsReady) { then.run(); return; }
        if (tts != null) { new android.os.Handler(android.os.Looper.getMainLooper()).postDelayed(() -> ensureTts(then), 300); return; }
        tts = new android.speech.tts.TextToSpeech(getContext(), status -> {
            ttsReady = status == android.speech.tts.TextToSpeech.SUCCESS;
            if (ttsReady) {
                tts.setLanguage(java.util.Locale.UK);
                pickVoice();
                tts.setSpeechRate(1.0f);
                tts.setPitch(0.92f);
            }
            then.run();
        });
    }

    /** Picks the most natural British male voice on the phone (Google's are best; avoids robotic ones). */
    private void pickVoice() {
        try {
            String[] pref = {"en-gb-x-rjs-network", "en-gb-x-gbd-network", "en-gb-x-rjs-local", "en-gb-x-gbd-local",
                             "en-gb-x-gbb-network", "en-gb-x-gbb-local"};
            java.util.Set<android.speech.tts.Voice> all = tts.getVoices();
            if (all == null) return;
            for (String want : pref)
                for (android.speech.tts.Voice v : all)
                    if (v.getName().equalsIgnoreCase(want) && !v.getFeatures().contains("notInstalled")) { tts.setVoice(v); return; }
            android.speech.tts.Voice best = null;
            for (android.speech.tts.Voice v : all) {
                if (!"GBR".equals(v.getLocale().getISO3Country()) || v.getFeatures().contains("notInstalled")) continue;
                String n = v.getName().toLowerCase();
                int score = v.getQuality() + (n.contains("male") && !n.contains("female") ? 200 : 0) - (v.isNetworkConnectionRequired() ? 0 : 50);
                if (best == null || score > best.getQuality()) best = v;
            }
            if (best != null) tts.setVoice(best);
        } catch (Exception ignored) { }
    }

    /** Speaks with the phone's own voice (used when the PC's natural voice isn't available). Resolves when done. */
    @PluginMethod
    public void speak(PluginCall call) {
        final String text = call.getString("text", "");
        final boolean inCall = Boolean.TRUE.equals(call.getBoolean("call", false));
        call.setKeepAlive(true);
        ensureTts(() -> {
            if (!ttsReady) { call.reject("no tts"); return; }
            String id = "orion" + System.nanoTime();
            tts.setOnUtteranceProgressListener(new android.speech.tts.UtteranceProgressListener() {
                @Override public void onStart(String u) { }
                @Override public void onDone(String u) { call.resolve(); }
                @Override public void onError(String u) { call.resolve(); }
            });
            android.os.Bundle p = new android.os.Bundle();
            p.putInt(android.speech.tts.TextToSpeech.Engine.KEY_PARAM_STREAM,
                    inCall ? android.media.AudioManager.STREAM_VOICE_CALL : android.media.AudioManager.STREAM_MUSIC);
            tts.speak(text, android.speech.tts.TextToSpeech.QUEUE_FLUSH, p, id);
        });
    }

    @PluginMethod
    public void stopSpeaking(PluginCall call) {
        if (tts != null) tts.stop();
        call.resolve();
    }

    // ---------------------------------------------------------------- music, battery, location, rides, school
    /** Control whatever's playing (Amazon Music, Spotify, YouTube…): next, previous, play, pause, playpause. */
    @PluginMethod
    public void media(PluginCall call) {
        String a = call.getString("action", "playpause");
        int code = "next".equals(a) ? android.view.KeyEvent.KEYCODE_MEDIA_NEXT
                : "previous".equals(a) ? android.view.KeyEvent.KEYCODE_MEDIA_PREVIOUS
                : "play".equals(a) ? android.view.KeyEvent.KEYCODE_MEDIA_PLAY
                : "pause".equals(a) ? android.view.KeyEvent.KEYCODE_MEDIA_PAUSE
                : android.view.KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE;
        android.media.AudioManager am = (android.media.AudioManager) getContext().getSystemService(Context.AUDIO_SERVICE);
        if ("louder".equals(a) || "quieter".equals(a)) {
            am.adjustStreamVolume(android.media.AudioManager.STREAM_MUSIC,
                    "louder".equals(a) ? android.media.AudioManager.ADJUST_RAISE : android.media.AudioManager.ADJUST_LOWER, 0);
        } else {
            am.dispatchMediaKeyEvent(new android.view.KeyEvent(android.view.KeyEvent.ACTION_DOWN, code));
            am.dispatchMediaKeyEvent(new android.view.KeyEvent(android.view.KeyEvent.ACTION_UP, code));
        }
        JSObject r = new JSObject();
        r.put("music", am.isMusicActive());
        call.resolve(r);
    }

    @PluginMethod
    public void battery(PluginCall call) {
        android.os.BatteryManager bm = (android.os.BatteryManager) getContext().getSystemService(Context.BATTERY_SERVICE);
        JSObject r = new JSObject();
        r.put("level", bm.getIntProperty(android.os.BatteryManager.BATTERY_PROPERTY_CAPACITY));
        r.put("charging", bm.isCharging());
        call.resolve(r);
    }

    @PluginMethod
    public void requestLocation(PluginCall call) {
        try {
            if (getActivity() != null) androidx.core.app.ActivityCompat.requestPermissions(getActivity(), new String[]{
                    android.Manifest.permission.ACCESS_FINE_LOCATION, android.Manifest.permission.ACCESS_COARSE_LOCATION}, 7001);
        } catch (Exception ignored) { }
        call.resolve();
    }

    @PluginMethod
    public void getLocation(PluginCall call) {
        android.location.Location l = LinkService.lastLocation(getContext());
        JSObject r = new JSObject();
        if (l != null) {
            r.put("lat", l.getLatitude()); r.put("lon", l.getLongitude()); r.put("acc", l.getAccuracy());
            r.put("age", (System.currentTimeMillis() - l.getTime()) / 1000);
        }
        r.put("ok", l != null);
        call.resolve(r);
    }

    /** Start timing a ride: the background link watches for you arriving (works with the screen off). */
    @PluginMethod
    public void startRide(PluginCall call) {
        getContext().getSharedPreferences(LinkService.PREFS, Context.MODE_PRIVATE).edit()
                .putBoolean("riding", true).putLong("ride_start", System.currentTimeMillis())
                .putFloat("dest_lat", call.getDouble("lat", 0.0).floatValue()).putFloat("dest_lon", call.getDouble("lon", 0.0).floatValue())
                .putFloat("dest_radius", call.getDouble("radius", 120.0).floatValue()).putString("ride_to", call.getString("to", "school")).apply();
        try { LinkService.start(getContext()); } catch (Exception ignored) { }
        call.resolve();
    }

    @PluginMethod
    public void stopRide(PluginCall call) {
        getContext().getSharedPreferences(LinkService.PREFS, Context.MODE_PRIVATE).edit().putBoolean("riding", false).remove("ride_d0").apply();
        NowBar.clear(getContext());
        call.resolve();
    }

    @PluginMethod
    public void rides(PluginCall call) {
        android.content.SharedPreferences sp = getContext().getSharedPreferences(LinkService.PREFS, Context.MODE_PRIVATE);
        JSObject r = new JSObject();
        r.put("rides", sp.getString("rides", ""));
        r.put("riding", sp.getBoolean("riding", false));
        call.resolve(r);
    }

    @PluginMethod
    public void setSchool(PluginCall call) {
        getContext().getSharedPreferences(LinkService.PREFS, Context.MODE_PRIVATE).edit()
                .putString("school_start", call.getString("start", "08:40")).putString("school_end", call.getString("end", "15:10"))
                .putBoolean("holiday", Boolean.TRUE.equals(call.getBoolean("holiday", false))).apply();
        call.resolve();
    }

    @PluginMethod
    public void openBatterySettings(PluginCall call) {
        try {
            Intent i = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:" + getContext().getPackageName()));
            launch(i);
        } catch (Exception e) {
            try { launch(new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)); } catch (Exception ignored) { }
        }
        call.resolve();
    }

    /** "Hey ORION" (beta): start/stop/pause the offline wake-word listener (started by name so the app still
     *  builds even if the wake-word engine isn't included). */
    @PluginMethod
    public void hotword(PluginCall call) {
        String a = call.getString("action", "on");
        Intent i = new Intent().setClassName(getContext(), "dev.kiyan.orion.HotwordService");
        try {
            if ("off".equals(a)) { getContext().stopService(i); call.resolve(); return; }
            if ("pause".equals(a)) i.setAction("dev.kiyan.orion.HOTWORD_PAUSE");
            if ("resume".equals(a)) i.setAction("dev.kiyan.orion.HOTWORD_RESUME");
            if (Build.VERSION.SDK_INT >= 26) getContext().startForegroundService(i); else getContext().startService(i);
            JSObject r = new JSObject(); r.put("ok", true); call.resolve(r);
        } catch (Exception e) {
            JSObject r = new JSObject(); r.put("ok", false); r.put("error", String.valueOf(e.getMessage())); call.resolve(r);
        }
    }

    // ---------------------------------------------------------------- wake-up call (runs with the PC off)
    @PluginMethod
    public void scheduleWake(PluginCall call) {
        SharedPreferences.Editor e = getContext().getSharedPreferences(LinkService.PREFS, Context.MODE_PRIVATE).edit();
        e.putBoolean("wake_on", Boolean.TRUE.equals(call.getBoolean("on", true)))
                .putString("wake", call.getString("wake", "08:00")).putString("wake_days", call.getString("days", "12345"))
                .putLong("holiday_until", call.getBoolean("holiday", false) ? System.currentTimeMillis() + 86400000L : 0).apply();
        WakeAlarm.schedule(getContext());
        JSObject r = new JSObject();
        r.put("next", getContext().getSharedPreferences(LinkService.PREFS, Context.MODE_PRIVATE).getLong("wake_next", 0));
        call.resolve(r);
    }

    // ---------------------------------------------------------------- Now Bar (Live Updates)
    @PluginMethod
    public void nowBar(PluginCall call) {
        NowBar.post(getContext(), call.getString("title", "ORION"), call.getString("text", ""), call.getString("chip", null),
                call.getInt("progress", -1), call.getInt("max", -1), call.getString("action", ""));
        call.resolve();
    }

    @PluginMethod
    public void nowBarClear(PluginCall call) {
        NowBar.clear(getContext());
        call.resolve();
    }

    // ---------------------------------------------------------------- messages read aloud on rides
    @PluginMethod
    public void notifAccess(PluginCall call) {
        try { launch(new Intent("android.settings.ACTION_NOTIFICATION_LISTENER_SETTINGS")); } catch (Exception ignored) { }
        call.resolve();
    }

    @PluginMethod
    public void notifStatus(PluginCall call) {
        JSObject r = new JSObject();
        String en = Settings.Secure.getString(getContext().getContentResolver(), "enabled_notification_listeners");
        r.put("enabled", en != null && en.contains(getContext().getPackageName()));
        r.put("connected", OrionNotifyService.connected);
        call.resolve(r);
    }

    @PluginMethod
    public void notifRecent(PluginCall call) {
        int since = call.getInt("since", 0);
        JSArray arr = new JSArray();
        int last = since;
        synchronized (OrionNotifyService.RECENT) {
            for (OrionNotifyService.Item it : OrionNotifyService.RECENT) {
                if (it.id <= since) continue;
                JSObject o = new JSObject();
                o.put("id", it.id); o.put("app", it.app); o.put("who", it.who); o.put("text", it.text);
                o.put("t", it.t); o.put("canReply", it.reply != null);
                arr.put(o); last = Math.max(last, it.id);
            }
        }
        JSObject r = new JSObject();
        r.put("items", arr); r.put("last", last);
        call.resolve(r);
    }

    @PluginMethod
    public void notifReply(PluginCall call) {
        JSObject r = new JSObject();
        r.put("ok", OrionNotifyService.reply(getContext(), call.getInt("id", -1), call.getString("text", "")));
        call.resolve(r);
    }

    /** Opens Android's "Digital assistant app" picker so ORION can be chosen (earbud press-and-hold). */
    @PluginMethod
    public void openAssistantSettings(PluginCall call) {
        try { launch(new Intent(Settings.ACTION_VOICE_INPUT_SETTINGS)); }
        catch (Exception e) { try { launch(new Intent(Settings.ACTION_MANAGE_DEFAULT_APPS_SETTINGS)); } catch (Exception ignored) { } }
        call.resolve();
    }

    @PluginMethod
    public void requestMic(PluginCall call) {
        try {
            if (getActivity() != null) androidx.core.app.ActivityCompat.requestPermissions(getActivity(),
                    new String[]{android.Manifest.permission.RECORD_AUDIO}, 7002);
        } catch (Exception ignored) { }
        call.resolve();
    }

    /** Call audio on the loudspeaker (Android puts it on the quiet earpiece while the mic is on). */
    @PluginMethod
    public void setSpeaker(PluginCall call) {
        boolean on = Boolean.TRUE.equals(call.getBoolean("on", true));
        boolean reset = Boolean.TRUE.equals(call.getBoolean("reset", false));
        try {
            android.media.AudioManager am = (android.media.AudioManager) getContext().getSystemService(Context.AUDIO_SERVICE);
            if (on) {
                am.setMode(android.media.AudioManager.MODE_IN_COMMUNICATION);
                int max = am.getStreamMaxVolume(android.media.AudioManager.STREAM_VOICE_CALL);
                if (am.getStreamVolume(android.media.AudioManager.STREAM_VOICE_CALL) < max * 0.7)
                    am.setStreamVolume(android.media.AudioManager.STREAM_VOICE_CALL, (int) Math.ceil(max * 0.8), 0);
            }
            if (Build.VERSION.SDK_INT >= 31) {
                if (on) {
                    for (android.media.AudioDeviceInfo d : am.getAvailableCommunicationDevices()) {
                        if (d.getType() == android.media.AudioDeviceInfo.TYPE_BUILTIN_SPEAKER) { am.setCommunicationDevice(d); break; }
                    }
                } else {
                    am.clearCommunicationDevice();
                }
            } else {
                am.setSpeakerphoneOn(on);
            }
            if (reset) am.setMode(android.media.AudioManager.MODE_NORMAL);
        } catch (Exception ignored) { }
        call.resolve();
    }

    /** Keep the phone linked to the PC in the background (calls + find my phone with the app closed). */
    @PluginMethod
    public void startLink(PluginCall call) {
        SharedPreferences.Editor e = getContext().getSharedPreferences(LinkService.PREFS, Context.MODE_PRIVATE).edit();
        e.putString("addr", call.getString("addr", "")).putString("addrs", call.getString("addrs", call.getString("addr", "")))
                .putString("pin", call.getString("pin", "")).putBoolean("on", true).apply();
        try {
            LinkService.start(getContext());
            JSObject ret = new JSObject();
            boolean fs = true;
            if (Build.VERSION.SDK_INT >= 34) {
                android.app.NotificationManager nm = (android.app.NotificationManager) getContext().getSystemService(Context.NOTIFICATION_SERVICE);
                fs = nm.canUseFullScreenIntent();
            }
            ret.put("fullScreen", fs);
            call.resolve(ret);
        } catch (Exception ex) { call.reject(ex.getMessage()); }
    }

    /** Android 14+: let ORION's calls appear full-screen (like a real incoming call). */
    @PluginMethod
    public void openFullScreenSettings(PluginCall call) {
        try {
            Intent i = Build.VERSION.SDK_INT >= 34
                    ? new Intent(Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT, Uri.parse("package:" + getContext().getPackageName()))
                    : new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, getContext().getPackageName());
            launch(i);
        } catch (Exception ex) { }
        call.resolve();
    }

    @PluginMethod
    public void stopLink(PluginCall call) {
        getContext().getSharedPreferences(LinkService.PREFS, Context.MODE_PRIVATE).edit().putBoolean("on", false).apply();
        getContext().stopService(new Intent(getContext(), LinkService.class));
        call.resolve();
    }

    @PluginMethod
    public void stopRing(PluginCall call) {
        Intent i = new Intent(getContext(), LinkService.class).setAction(LinkService.STOP_RING);
        try { if (Build.VERSION.SDK_INT >= 26) getContext().startForegroundService(i); else getContext().startService(i); }
        catch (Exception ignored) { }
        call.resolve();
    }

    @PluginMethod
    public void copyText(PluginCall call) {
        ClipboardManager cm = (ClipboardManager) getContext().getSystemService(Context.CLIPBOARD_SERVICE);
        cm.setPrimaryClip(ClipData.newPlainText("ORION", call.getString("text", "")));
        call.resolve();
    }

    @PluginMethod
    public void readClipboard(PluginCall call) {
        ClipboardManager cm = (ClipboardManager) getContext().getSystemService(Context.CLIPBOARD_SERVICE);
        JSObject ret = new JSObject();
        String t = "";
        try {
            ClipData d = cm.getPrimaryClip();
            if (d != null && d.getItemCount() > 0 && d.getItemAt(0).getText() != null) t = d.getItemAt(0).getText().toString();
        } catch (Exception ignored) { }
        ret.put("text", t);
        call.resolve(ret);
    }

    /** Save a file the PC sent to the phone's Downloads folder. */
    @PluginMethod
    public void download(PluginCall call) {
        try {
            String name = call.getString("name", "file");
            DownloadManager.Request r = new DownloadManager.Request(Uri.parse(call.getString("url", "")));
            r.addRequestHeader("X-PIN", call.getString("pin", ""));
            r.setTitle(name);
            r.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            r.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, "ORION/" + name);
            ((DownloadManager) getContext().getSystemService(Context.DOWNLOAD_SERVICE)).enqueue(r);
            call.resolve();
        } catch (Exception ex) { call.reject(ex.getMessage()); }
    }
}
