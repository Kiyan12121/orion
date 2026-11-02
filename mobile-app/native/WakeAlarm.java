package dev.kiyan.orion;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;

import java.util.Calendar;

/**
 * The morning wake-up call, run entirely by the phone (the PC and laptop can be off all night).
 * Uses Android's alarm-clock alarm, so it fires on time even in deep sleep, then ORION rings like a call.
 */
public class WakeAlarm extends BroadcastReceiver {
    static final String ACTION = "dev.kiyan.orion.WAKE";

    static void schedule(Context c) {
        SharedPreferences sp = c.getSharedPreferences(LinkService.PREFS, Context.MODE_PRIVATE);
        AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
        PendingIntent pi = PendingIntent.getBroadcast(c, 9301, new Intent(c, WakeAlarm.class).setAction(ACTION),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        am.cancel(pi);
        if (!sp.getBoolean("wake_on", true)) return;
        String wake = sp.getString("wake", "08:00");
        String days = sp.getString("wake_days", "12345");          // 1 = Monday … 7 = Sunday
        long holidayUntil = sp.getLong("holiday_until", 0);
        int hh = Integer.parseInt(wake.substring(0, 2)), mm = Integer.parseInt(wake.substring(3, 5));
        Calendar at = Calendar.getInstance();
        at.set(Calendar.HOUR_OF_DAY, hh); at.set(Calendar.MINUTE, mm); at.set(Calendar.SECOND, 0); at.set(Calendar.MILLISECOND, 0);
        for (int k = 0; k < 15; k++) {
            int dow = at.get(Calendar.DAY_OF_WEEK);                  // Sunday = 1
            int iso = dow == Calendar.SUNDAY ? 7 : dow - 1;
            if (at.getTimeInMillis() > System.currentTimeMillis() + 30000 && days.contains(String.valueOf(iso))
                    && at.getTimeInMillis() > holidayUntil) break;
            at.add(Calendar.DAY_OF_MONTH, 1);
        }
        sp.edit().putLong("wake_next", at.getTimeInMillis()).apply();
        PendingIntent show = PendingIntent.getActivity(c, 9302, new Intent(c, MainActivity.class),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        try {
            am.setAlarmClock(new AlarmManager.AlarmClockInfo(at.getTimeInMillis(), show), pi);
        } catch (SecurityException e) {                              // exact alarms not allowed → close enough
            if (Build.VERSION.SDK_INT >= 23) am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at.getTimeInMillis(), pi);
            else am.set(AlarmManager.RTC_WAKEUP, at.getTimeInMillis(), pi);
        }
    }

    @Override
    public void onReceive(Context c, Intent i) {
        if (ACTION.equals(i.getAction())) {
            Intent s = new Intent(c, LinkService.class).setAction(LinkService.WAKE_CALL);
            try {
                if (Build.VERSION.SDK_INT >= 26) c.startForegroundService(s); else c.startService(s);
            } catch (Exception ignored) { }
        }
        schedule(c);                                                 // and set tomorrow's (also runs after a restart)
    }
}
