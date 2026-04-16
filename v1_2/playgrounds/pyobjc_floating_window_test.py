from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyRegular,
    NSWindow,
    NSWindowStyleMaskTitled,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable,
    NSBackingStoreBuffered,
    NSFloatingWindowLevel,
    NSTextField,
    NSView,
    NSColor,
    NSButton,
    NSBezelStyleRounded,
    NSFont,
    NSApp,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
)
from Foundation import NSObject, NSMakeRect
import objc


class AppDelegate(NSObject):
    window = objc.ivar()
    output_field = objc.ivar()
    input_field = objc.ivar()

    def applicationDidFinishLaunching_(self, notification):
        frame = NSMakeRect(200.0, 500.0, 460.0, 220.0)
        style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskResizable

        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            style,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_("Remi PyObjC Floating Test")
        self.window.setLevel_(NSFloatingWindowLevel)
        self.window.setReleasedWhenClosed_(False)
        self.window.setOpaque_(True)
        self.window.setBackgroundColor_(NSColor.colorWithRed_green_blue_alpha_(0.12, 0.12, 0.12, 1.0))

        # 让窗口尽可能跨桌面/全屏场景保持可见
        behavior = (
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        self.window.setCollectionBehavior_(behavior)

        content = self.window.contentView()

        self.output_field = NSTextField.alloc().initWithFrame_(NSMakeRect(20.0, 95.0, 420.0, 95.0))
        self.output_field.setStringValue_("窗口已启动（PyObjC）")
        self.output_field.setEditable_(False)
        self.output_field.setSelectable_(False)
        self.output_field.setBezeled_(True)
        self.output_field.setDrawsBackground_(True)
        self.output_field.setBackgroundColor_(NSColor.colorWithRed_green_blue_alpha_(0.16, 0.16, 0.16, 1.0))
        self.output_field.setTextColor_(NSColor.whiteColor())
        self.output_field.setFont_(NSFont.systemFontOfSize_(14.0))
        content.addSubview_(self.output_field)

        self.input_field = NSTextField.alloc().initWithFrame_(NSMakeRect(20.0, 45.0, 320.0, 32.0))
        self.input_field.setPlaceholderString_("输入文字后点击发送")
        self.input_field.setFont_(NSFont.systemFontOfSize_(14.0))
        content.addSubview_(self.input_field)

        send_btn = NSButton.alloc().initWithFrame_(NSMakeRect(350.0, 45.0, 90.0, 32.0))
        send_btn.setTitle_("发送")
        send_btn.setBezelStyle_(NSBezelStyleRounded)
        send_btn.setTarget_(self)
        send_btn.setAction_("onSend:")
        content.addSubview_(send_btn)

        self.window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    def onSend_(self, sender):
        text = self.input_field.stringValue().strip()
        if not text:
            return
        self.output_field.setStringValue_(f"你输入了: {text}")
        self.input_field.setStringValue_("")


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)

    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()
