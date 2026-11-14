using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;

// Only Windows' system-notification sessions are muted; endpoint/app volumes are untouched.
public sealed class OrinSystemSoundGuard : IDisposable {
    [ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IDeviceEnumerator {
        [PreserveSig] int EnumAudioEndpoints(int flow, int state, out IDeviceCollection devices);
        [PreserveSig] int GetDefaultAudioEndpoint(int flow, int role, out IDevice device);
    }
    [ComImport, Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IDeviceCollection {
        [PreserveSig] int GetCount(out int count);
        [PreserveSig] int Item(int index, out IDevice device);
    }
    [ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IDevice {
        [PreserveSig] int Activate(ref Guid iid, int context, IntPtr parameters, [MarshalAs(UnmanagedType.IUnknown)] out object value);
        [PreserveSig] int OpenPropertyStore(int access, out IntPtr store);
        [PreserveSig] int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id);
        [PreserveSig] int GetState(out int state);
    }
    [ComImport, Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface ISessionManager {
        [PreserveSig] int GetAudioSessionControl(ref Guid session, uint flags, out IntPtr control);
        [PreserveSig] int GetSimpleAudioVolume(ref Guid session, uint flags, out IntPtr volume);
        [PreserveSig] int GetSessionEnumerator(out ISessionEnumerator sessions);
    }
    [ComImport, Guid("E2F5BB11-0570-40CA-ACDD-3AA01277DEE8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface ISessionEnumerator {
        [PreserveSig] int GetCount(out int count);
        [PreserveSig] int GetSession(int index, [MarshalAs(UnmanagedType.IUnknown)] out object session);
    }
    [ComImport, Guid("BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IControl {
        [PreserveSig] int GetState(out int state);
        [PreserveSig] int GetDisplayName([MarshalAs(UnmanagedType.LPWStr)] out string name);
        [PreserveSig] int SetDisplayName([MarshalAs(UnmanagedType.LPWStr)] string name, ref Guid context);
        [PreserveSig] int GetIconPath([MarshalAs(UnmanagedType.LPWStr)] out string path);
        [PreserveSig] int SetIconPath([MarshalAs(UnmanagedType.LPWStr)] string path, ref Guid context);
        [PreserveSig] int GetGroupingParam(out Guid group);
        [PreserveSig] int SetGroupingParam(ref Guid group, ref Guid context);
        [PreserveSig] int RegisterAudioSessionNotification(IntPtr client);
        [PreserveSig] int UnregisterAudioSessionNotification(IntPtr client);
        [PreserveSig] int GetSessionIdentifier([MarshalAs(UnmanagedType.LPWStr)] out string id);
        [PreserveSig] int GetSessionInstanceIdentifier([MarshalAs(UnmanagedType.LPWStr)] out string id);
        [PreserveSig] int GetProcessId(out uint process);
        [PreserveSig] int IsSystemSoundsSession();
    }
    [ComImport, Guid("87CE5498-68D6-44E5-9215-6DA47EF883D8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IVolume {
        [PreserveSig] int SetMasterVolume(float value, ref Guid context);
        [PreserveSig] int GetMasterVolume(out float value);
        [PreserveSig] int SetMute([MarshalAs(UnmanagedType.Bool)] bool value, ref Guid context);
        [PreserveSig] int GetMute([MarshalAs(UnmanagedType.Bool)] out bool value);
    }
    [ComImport, Guid("C02216F6-8C67-4B5B-9D00-D008E73E0064"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IMeter { [PreserveSig] int GetPeakValue(out float value); }

    public sealed class Snapshot {
        public int Number;
        public bool InitiallyMuted;
        public bool MutedDuring;
        public bool Restored;
    }
    private sealed class Saved {
        public IVolume Volume;
        public IMeter Meter;
        public Snapshot Report;
    }
    private readonly List<Saved> saved = new List<Saved>();
    public readonly List<string> Errors = new List<string>();
    public bool TailQuiet = false;
    private bool disposed;
    private static void Check(int hr) { Marshal.ThrowExceptionForHR(hr); }

    public OrinSystemSoundGuard() {
        try {
            var enumerator = (IDeviceEnumerator)Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")));
            IDeviceCollection devices; Check(enumerator.EnumAudioEndpoints(0, 1, out devices));
            int deviceCount; Check(devices.GetCount(out deviceCount));
            for (int d = 0; d < deviceCount; d++) {
                IDevice device; Check(devices.Item(d, out device));
                var iid = new Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F");
                object managerObject; Check(device.Activate(ref iid, 23, IntPtr.Zero, out managerObject));
                ISessionEnumerator sessions; Check(((ISessionManager)managerObject).GetSessionEnumerator(out sessions));
                int count; Check(sessions.GetCount(out count));
                for (int n = 0; n < count; n++) {
                    object session; Check(sessions.GetSession(n, out session));
                    var control = (IControl)session;
                    if (control.IsSystemSoundsSession() != 0) continue;
                    var volume = (IVolume)session;
                    bool before; Check(volume.GetMute(out before));
                    var state = new Saved { Volume = volume, Meter = session as IMeter,
                        Report = new Snapshot { Number = saved.Count, InitiallyMuted = before } };
                    saved.Add(state); // Save original state before the first change.
                    var context = Guid.Empty; Check(volume.SetMute(true, ref context));
                    bool muted; Check(volume.GetMute(out muted));
                    state.Report.MutedDuring = muted;
                    if (!muted) throw new InvalidOperationException("System-sound mute readback failed");
                }
            }
            if (saved.Count == 0) throw new InvalidOperationException("No system-sound session found; refusing audible tests");
        } catch { Dispose(); throw; }
    }
    public Snapshot[] Snapshots() { return saved.ConvertAll(s => s.Report).ToArray(); }
    public void WaitForQuiet() {
        var timer = Stopwatch.StartNew(); long quietSince = -1;
        while (timer.ElapsedMilliseconds < 4000) {
            bool quiet = true;
            foreach (var state in saved) {
                float peak;
                if (state.Meter == null || state.Meter.GetPeakValue(out peak) < 0 || peak > 0.00001f) quiet = false;
            }
            if (quiet) {
                if (quietSince < 0) quietSince = timer.ElapsedMilliseconds;
                if (timer.ElapsedMilliseconds - quietSince >= 350) { TailQuiet = true; return; }
            } else quietSince = -1;
            Thread.Sleep(25);
        }
    }
    public void Dispose() {
        if (disposed) return;
        disposed = true;
        foreach (var state in saved) {
            try {
                var context = Guid.Empty;
                Check(state.Volume.SetMute(state.Report.InitiallyMuted, ref context));
                bool after; Check(state.Volume.GetMute(out after));
                state.Report.Restored = after == state.Report.InitiallyMuted;
                if (!state.Report.Restored) Errors.Add("Mute restoration readback mismatch");
            } catch (Exception error) { Errors.Add(error.GetType().Name + ": " + error.Message); }
        }
    }
}
