package ru.mytra.rks;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(CameraStreamPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
