package ru.mytra.rks

import android.Manifest
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import android.util.Base64
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.exifinterface.media.ExifInterface
import com.getcapacitor.JSObject
import com.getcapacitor.PermissionState
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import com.getcapacitor.annotation.Permission
import java.io.ByteArrayOutputStream
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.Executors

// Нативный снимок из видеопотока CameraX: превью → стоп-кадр → ресайз 1600px →
// «юбка» (оранжевая полоса, белый текст) → JPEG + EXIF GPS.
@CapacitorPlugin(
    name = "CameraStream",
    permissions = [Permission(strings = [Manifest.permission.CAMERA], alias = "camera")]
)
class CameraStreamPlugin : Plugin() {

    private var overlay: FrameLayout? = null
    private var previewView: PreviewView? = null
    private var imageCapture: ImageCapture? = null
    private var cameraProvider: ProcessCameraProvider? = null
    private var pendingCall: PluginCall? = null
    private var skirtText = ""
    private var lat = 0.0
    private var lng = 0.0
    private val executor = Executors.newSingleThreadExecutor()

    @PluginMethod
    fun start(call: PluginCall) {
        pendingCall = call
        skirtText = call.getString("skirtText") ?: ""
        lat = call.getDouble("lat") ?: 0.0
        lng = call.getDouble("lng") ?: 0.0
        if (getPermissionState("camera") != PermissionState.GRANTED) {
            requestPermissionForAlias("camera", call, "cameraPermissionCallback")
            return
        }
        showPreview()
    }

    @PluginMethod
    fun cameraPermissionCallback(call: PluginCall) {
        if (getPermissionState("camera") == PermissionState.GRANTED) {
            showPreview()
        } else {
            pendingCall?.reject("Доступ к камере запрещён")
            pendingCall = null
        }
        call.resolve()
    }

    @PluginMethod
    fun stop(call: PluginCall) {
        hidePreview()
        pendingCall?.resolve(JSObject().put("cancelled", true))
        pendingCall = null
        call.resolve()
    }

    private fun showPreview() {
        val act = activity
        if (act == null) {
            pendingCall?.reject("Нет activity")
            pendingCall = null
            return
        }
        act.runOnUiThread {
            val root = act.window.decorView.findViewById<ViewGroup>(android.R.id.content)
            val ov = FrameLayout(act)
            ov.setBackgroundColor(Color.BLACK)

            val pv = PreviewView(act)
            ov.addView(pv, FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))

            val btnBar = LinearLayout(act)
            btnBar.orientation = LinearLayout.HORIZONTAL
            btnBar.setBackgroundColor(Color.parseColor("#CC000000"))
            btnBar.setPadding(dp(8), dp(8), dp(8), dp(8))
            val cancel = Button(act)
            cancel.text = "Отмена"
            cancel.setOnClickListener {
                hidePreview()
                pendingCall?.resolve(JSObject().put("cancelled", true))
                pendingCall = null
            }
            val capture = Button(act)
            capture.text = "Снять"
            capture.setOnClickListener { capturePhoto() }
            btnBar.addView(cancel, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            btnBar.addView(capture, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            ov.addView(btnBar, FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM))

            root.addView(ov, FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
            overlay = ov
            previewView = pv
            startCamera()
        }
    }

    private fun startCamera() {
        val act = activity ?: return
        val future = ProcessCameraProvider.getInstance(act)
        future.addListener({
            try {
                val provider = future.get()
                cameraProvider = provider
                val pv = previewView ?: return@addListener
                val preview = Preview.Builder().build().also { it.surfaceProvider = pv.surfaceProvider }
                val capture = ImageCapture.Builder().setTargetRotation(pv.display.rotation).build()
                imageCapture = capture
                provider.unbindAll()
                provider.bindToLifecycle(act, CameraSelector.DEFAULT_BACK_CAMERA, preview, capture)
            } catch (e: Exception) {
                hidePreview()
                pendingCall?.reject("Ошибка камеры: ${e.message}")
                pendingCall = null
            }
        }, ContextCompat.getMainExecutor(act))
    }

    private fun capturePhoto() {
        val capture = imageCapture ?: return
        val file = File.createTempFile("mytra_capture", ".jpg", context.cacheDir)
        val output = ImageCapture.OutputFileOptions.Builder(file).build()
        capture.takePicture(output, executor, object : ImageCapture.OnImageSavedCallback {
            override fun onImageSaved(results: ImageCapture.OutputFileResults) {
                try {
                    val bmp = BitmapFactory.decodeFile(file.absolutePath)
                        ?: throw IllegalStateException("Не удалось декодировать снимок")
                    val resized = resizeTo1600(bmp)
                    val withSkirt = addSkirt(resized)
                    val dataUrl = encodeJpeg(withSkirt)
                    resized.recycle()
                    withSkirt.recycle()

                    val res = JSObject().put("dataUrl", dataUrl)
                    hidePreview()
                    pendingCall?.resolve(res)
                    pendingCall = null
                } catch (e: Exception) {
                    hidePreview()
                    pendingCall?.reject("Ошибка обработки: ${e.message}")
                    pendingCall = null
                } finally {
                    file.delete()
                }
            }

            override fun onError(exc: ImageCaptureException) {
                file.delete()
                hidePreview()
                pendingCall?.reject("Ошибка съёмки: ${exc.message}")
                pendingCall = null
            }
        })
    }

    private fun hidePreview() {
        val act = activity ?: return
        act.runOnUiThread {
            try {
                cameraProvider?.unbindAll()
            } catch (_: Exception) {
            }
            cameraProvider = null
            imageCapture = null
            previewView = null
            val ov = overlay
            if (ov != null) (ov.parent as? ViewGroup)?.removeView(ov)
            overlay = null
        }
    }

    private fun resizeTo1600(src: Bitmap): Bitmap {
        val longSide = maxOf(src.width, src.height)
        if (longSide <= 1600) return src
        val scale = 1600f / longSide
        val nw = Math.round(src.width * scale)
        val nh = Math.round(src.height * scale)
        val resized = Bitmap.createScaledBitmap(src, nw, nh, true)
        if (resized !== src) src.recycle()
        return resized
    }

    private fun addSkirt(src: Bitmap): Bitmap {
        val density = context.resources.displayMetrics.density
        val barH = Math.round(32f * density)
        val out = Bitmap.createBitmap(src.width, src.height + barH, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(out)
        canvas.drawBitmap(src, 0f, 0f, null)

        val bg = Paint().apply { color = Color.parseColor("#F47B20") }
        canvas.drawRect(0f, src.height.toFloat(), out.width.toFloat(), out.height.toFloat(), bg)

        val text = skirtText.ifBlank {
            SimpleDateFormat("dd.MM.yyyy HH:mm", Locale.getDefault()).format(Date())
        }
        val textPaint = Paint().apply {
            color = Color.WHITE
            textSize = 13f * density
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
            isAntiAlias = true
        }
        val baseline = src.height + barH / 2f - (textPaint.descent() + textPaint.ascent()) / 2f
        canvas.drawText(text, 8f * density, baseline, textPaint)
        return out
    }

    private fun encodeJpeg(bitmap: Bitmap): String {
        val bos = ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.JPEG, 86, bos)
        val bytes = bos.toByteArray()

        if (lat != 0.0 || lng != 0.0) {
            try {
                val tmp = File.createTempFile("mytra", ".jpg", context.cacheDir)
                tmp.writeBytes(bytes)
                val exif = ExifInterface(tmp.absolutePath)
                exif.setLatLong(lat, lng)
                exif.saveAttributes()
                val finalBytes = tmp.readBytes()
                tmp.delete()
                return "data:image/jpeg;base64," + Base64.encodeToString(finalBytes, Base64.NO_WRAP)
            } catch (_: Exception) {
            }
        }
        return "data:image/jpeg;base64," + Base64.encodeToString(bytes, Base64.NO_WRAP)
    }

    private fun dp(value: Int): Int = Math.round(value * context.resources.displayMetrics.density)
}
