#ifndef WINDOWS_VR_DESKTOP_H
#define WINDOWS_VR_DESKTOP_H

/* The flat Windows session's initial virtual monitor. Guest display-mode
 * changes can still publish a different live size through IOSDisplayShim. */
enum { WVR_DESKTOP_WIDTH = 1280, WVR_DESKTOP_HEIGHT = 720 };

#endif /* WINDOWS_VR_DESKTOP_H */
