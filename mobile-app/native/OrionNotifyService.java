package dev.kiyan.orion;

import android.app.Notification;
import android.app.PendingIntent;
import android.app.RemoteInput;
import android.content.Intent;
import android.os.Bundle;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;

import java.util.ArrayList;
import java.util.List;

/**
 * Lets ORION read out messages that arrive while you're riding (Snapchat, WhatsApp, Instagram, Discord, texts…)
 * and reply to them by voice using the notification's own Reply button. Only runs if you switch it on in
 * Android settings. Nothing is uploaded: messages stay on the phone.
 */
public class OrionNotifyService extends NotificationListenerService {
    static final String[] CHAT_APPS = {"com.snapchat.android", "com.whatsapp", "com.instagram.android", "com.discord",
            "com.google.android.apps.messaging", "com.samsung.android.messaging", "org.telegram.messenger",
            "com.facebook.orca", "com.microsoft.teams", "com.google.android.gm"};
    static final List<Item> RECENT = new ArrayList<>();
    static volatile boolean connected = false;
    static int seq = 0;

    static class Item {
        int id; String app; String pkg; String who; String text; long t; Notification.Action reply;
    }

    static String appName(String pkg) {
        switch (pkg) {
            case "com.snapchat.android": return "Snapchat";
            case "com.whatsapp": return "WhatsApp";
            case "com.instagram.android": return "Instagram";
            case "com.discord": return "Discord";
            case "org.telegram.messenger": return "Telegram";
            case "com.facebook.orca": return "Messenger";
            case "com.microsoft.teams": return "Teams";
            case "com.google.android.gm": return "Gmail";
            default: return "Messages";
        }
    }

    @Override public void onListenerConnected() { connected = true; }
    @Override public void onListenerDisconnected() { connected = false; }

    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        try {
            String pkg = sbn.getPackageName();
            boolean chat = false;
            for (String a : CHAT_APPS) if (a.equals(pkg)) { chat = true; break; }
            if (!chat) return;
            Notification n = sbn.getNotification();
            if ((n.flags & Notification.FLAG_GROUP_SUMMARY) != 0) return;
            Bundle ex = n.extras;
            CharSequence title = ex.getCharSequence(Notification.EXTRA_TITLE);
            CharSequence text = ex.getCharSequence(Notification.EXTRA_TEXT);
            CharSequence big = ex.getCharSequence(Notification.EXTRA_BIG_TEXT);
            if (title == null || (text == null && big == null)) return;
            String body = String.valueOf(big != null ? big : text);
            if (body.toLowerCase().contains("@everyone") || body.toLowerCase().contains("@here")) return;
            Notification.Action reply = null;
            if (n.actions != null) for (Notification.Action a : n.actions)
                if (a.getRemoteInputs() != null && a.getRemoteInputs().length > 0) { reply = a; break; }
            Item it = new Item();
            it.id = ++seq; it.pkg = pkg; it.app = appName(pkg); it.who = String.valueOf(title);
            it.text = body.length() > 400 ? body.substring(0, 400) : body; it.t = System.currentTimeMillis(); it.reply = reply;
            synchronized (RECENT) {
                for (Item o : RECENT) if (o.who.equals(it.who) && o.text.equals(it.text) && it.t - o.t < 60000) return;
                RECENT.add(it);
                while (RECENT.size() > 40) RECENT.remove(0);
            }
        } catch (Exception ignored) { }
    }

    /** Replies through the app's own notification Reply box. */
    static boolean reply(android.content.Context ctx, int id, String message) {
        Item it = null;
        synchronized (RECENT) { for (Item o : RECENT) if (o.id == id) it = o; }
        if (it == null || it.reply == null) return false;
        try {
            Intent fill = new Intent();
            Bundle res = new Bundle();
            for (RemoteInput ri : it.reply.getRemoteInputs()) res.putCharSequence(ri.getResultKey(), message);
            RemoteInput.addResultsToIntent(it.reply.getRemoteInputs(), fill, res);
            it.reply.actionIntent.send(ctx, 0, fill);
            return true;
        } catch (PendingIntent.CanceledException e) {
            return false;
        }
    }
}
