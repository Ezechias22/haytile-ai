'use client';

import { useEffect } from 'react';

/** Hold only a visible, active call awake; never keep the screen on after it ends. */
export function useScreenWakeLock(active: boolean) {
  useEffect(() => {
    if (!active || !navigator.wakeLock) return;
    let disposed = false;
    let pending = false;
    let lock: WakeLockSentinel | null = null;
    const acquire = async () => {
      if (disposed || pending || document.visibilityState !== 'visible' || (lock && !lock.released)) return;
      pending = true;
      try {
        const granted = await navigator.wakeLock.request('screen');
        if (disposed || document.visibilityState !== 'visible') {
          await granted.release();
          return;
        }
        lock = granted;
        granted.addEventListener('release', () => { if (lock === granted) lock = null; });
      } catch {
        // Unsupported devices, power-saving policy or a denied request must not end the call.
      } finally { pending = false; }
    };
    const visible = () => { if (document.visibilityState === 'visible') void acquire(); };
    document.addEventListener('visibilitychange', visible);
    void acquire();
    return () => {
      disposed = true;
      document.removeEventListener('visibilitychange', visible);
      const previous = lock;
      lock = null;
      if (previous) void previous.release().catch(() => {});
    };
  }, [active]);
}
