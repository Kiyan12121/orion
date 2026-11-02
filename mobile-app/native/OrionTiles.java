package dev.kiyan.orion;

import android.app.PendingIntent;
import android.content.Intent;
import android.os.Build;
import android.service.quicksettings.Tile;
import android.service.quicksettings.TileService;
import android.view.KeyEvent;

/** Quick Settings tiles (pull down from the top of the screen): Ask ORION, Ride mode, Skip song. */
public class OrionTiles {
    static void launch(TileService s, String action) {
        Intent i = new Intent(s, MainActivity.class);
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
        i.putExtra("orion_action", action);
        if (Build.VERSION.SDK_INT >= 34) {
            PendingIntent pi = PendingIntent.getActivity(s, action.hashCode(), i,
                    PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
            s.startActivityAndCollapse(pi);
        } else {
            s.startActivityAndCollapse(i);
        }
    }

    static void label(TileService s, String text) {
        Tile t = s.getQsTile();
        if (t == null) return;
        t.setLabel(text);
        t.setState(Tile.STATE_INACTIVE);
        t.updateTile();
    }

    public static class Ask extends TileService {
        @Override public void onStartListening() { label(this, "Ask ORION"); }
        @Override public void onClick() { launch(this, "listen"); }
    }

    public static class Ride extends TileService {
        @Override public void onStartListening() { label(this, "Ride mode"); }
        @Override public void onClick() { launch(this, "ride"); }
    }

    public static class Skip extends TileService {
        @Override public void onStartListening() { label(this, "Skip song"); }
        @Override public void onClick() {
            android.media.AudioManager am = (android.media.AudioManager) getSystemService(AUDIO_SERVICE);
            am.dispatchMediaKeyEvent(new KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_MEDIA_NEXT));
            am.dispatchMediaKeyEvent(new KeyEvent(KeyEvent.ACTION_UP, KeyEvent.KEYCODE_MEDIA_NEXT));
        }
    }
}
