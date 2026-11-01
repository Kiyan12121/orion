package dev.kiyan.orion;

import android.content.Intent;
import android.speech.RecognitionService;

/** Required by Android for an assistant app; ORION does its own listening in the app. */
public class OrionRecognitionService extends RecognitionService {
    @Override protected void onStartListening(Intent recognizerIntent, Callback listener) { }
    @Override protected void onCancel(Callback listener) { }
    @Override protected void onStopListening(Callback listener) { }
}
