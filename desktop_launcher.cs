using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Web.Script.Serialization;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

internal sealed class StartupResult
{
    public string Url;
    public string Error;
}

internal sealed class StartupSplash : Form
{
    private readonly Label _status;
    private readonly ProgressBar _progress;
    private readonly System.Windows.Forms.Timer _timer;
    private readonly string[] _statuses = new string[]
    {
        "Veritabanı bağlantısı doğrulanıyor...",
        "Stok ve Teknik Servis modülleri yükleniyor...",
        "BAYSÖZ YAZILIM KVKK Güvenlik Kalkanı aktif..."
    };
    private int _statusIndex;
    private int _progressValue;

    public StartupSplash()
    {
        Text = "LAVOX ELEKTRONİK ERP";
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.CenterScreen;
        ClientSize = new Size(620, 310);
        BackColor = Color.FromArgb(17, 29, 49);
        ShowInTaskbar = true;
        TopMost = true;

        Label brand = new Label();
        brand.AutoSize = false;
        brand.Location = new Point(42, 42);
        brand.Size = new Size(536, 42);
        brand.ForeColor = Color.White;
        brand.Font = new Font("Segoe UI", 19, FontStyle.Bold);
        brand.Text = "LAVOX ELEKTRONİK";
        Controls.Add(brand);

        Label title = new Label();
        title.AutoSize = false;
        title.Location = new Point(44, 91);
        title.Size = new Size(520, 28);
        title.ForeColor = Color.FromArgb(177, 194, 221);
        title.Font = new Font("Segoe UI", 11, FontStyle.Regular);
        title.Text = "Kurumsal ERP v2.0  |  BAYSÖZ YAZILIM";
        Controls.Add(title);

        Panel separator = new Panel();
        separator.Location = new Point(44, 139);
        separator.Size = new Size(530, 1);
        separator.BackColor = Color.FromArgb(70, 91, 126);
        Controls.Add(separator);

        _status = new Label();
        _status.AutoSize = false;
        _status.Location = new Point(44, 165);
        _status.Size = new Size(530, 25);
        _status.ForeColor = Color.FromArgb(204, 216, 238);
        _status.Font = new Font("Segoe UI", 9, FontStyle.Regular);
        _status.Text = _statuses[0];
        Controls.Add(_status);

        _progress = new ProgressBar();
        _progress.Location = new Point(44, 203);
        _progress.Size = new Size(530, 8);
        _progress.Minimum = 0;
        _progress.Maximum = 100;
        _progress.Style = ProgressBarStyle.Continuous;
        Controls.Add(_progress);

        Label footer = new Label();
        footer.AutoSize = false;
        footer.Location = new Point(44, 238);
        footer.Size = new Size(530, 20);
        footer.ForeColor = Color.FromArgb(118, 139, 173);
        footer.Font = new Font("Segoe UI", 8, FontStyle.Regular);
        footer.Text = "Güvenli yerel ERP çalışma alanı hazırlanıyor";
        Controls.Add(footer);

        _timer = new System.Windows.Forms.Timer();
        _timer.Interval = 950;
        _timer.Tick += AdvanceProgress;
        _timer.Start();
    }

    private void AdvanceProgress(object sender, EventArgs e)
    {
        _progressValue = Math.Min(90, _progressValue + 3);
        _progress.Value = _progressValue;
        if (_progressValue > 0 && _progressValue % 18 == 0)
        {
            _statusIndex = (_statusIndex + 1) % _statuses.Length;
            _status.Text = _statuses[_statusIndex];
        }
    }

    public void SetReady()
    {
        _timer.Stop();
        _progress.Value = 100;
        _status.Text = "ERP hazır. Güvenli oturum açma penceresi başlatılıyor...";
    }

    protected override void OnFormClosed(FormClosedEventArgs e)
    {
        _timer.Stop();
        _timer.Dispose();
        base.OnFormClosed(e);
    }
}

internal sealed class LauncherContext : ApplicationContext
{
    private const int PreferredPort = 8010;
    private readonly string _installRoot;
    private readonly string _dataRoot;
    private readonly string _startupLogPath;
    private readonly StartupSplash _splash;
    private readonly NotifyIcon _trayIcon;
    private Process _backendProcess;
    private readonly object _processLock = new object();
    private string _appUrl;
    private volatile bool _exiting;

    public LauncherContext()
    {
        _installRoot = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(
            Path.DirectorySeparatorChar,
            Path.AltDirectorySeparatorChar
        );
        _dataRoot = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Lavox_ERP"
        );
        _startupLogPath = Path.Combine(_dataRoot, "startup.log");
        Directory.CreateDirectory(_dataRoot);
        AppendStartupLog(
            _startupLogPath,
            "[" + DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ") + "] Lavox ERP başlatma oturumu başlatıldı."
        );
        _splash = new StartupSplash();
        _backendProcess = null;

        ContextMenuStrip menu = new ContextMenuStrip();
        menu.Items.Add("Lavox ERP'yi Aç", null, OpenApplication);
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("ERP ve arka ucu kapat", null, ExitApplication);

        Icon appIcon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        _trayIcon = new NotifyIcon();
        _trayIcon.Icon = appIcon ?? SystemIcons.Application;
        _trayIcon.Text = "LAVOX ELEKTRONİK Kurumsal ERP";
        _trayIcon.ContextMenuStrip = menu;
        _trayIcon.DoubleClick += OpenApplication;
        _trayIcon.Visible = false;

        _splash.FormClosed += SplashClosed;
        _splash.Shown += BeginStartup;
        _splash.Show();
    }

    private void BeginStartup(object sender, EventArgs e)
    {
        ThreadPool.QueueUserWorkItem(delegate
        {
            StartupResult result = new StartupResult();
            try
            {
                result.Url = StartBackend();
                if (!_exiting)
                {
                    OpenAppWindow(result.Url);
                }
            }
            catch (WebException)
            {
                result.Error = "Yerel ERP bağlantısı kurulamadı.";
            }
            catch (IOException)
            {
                result.Error = "Kurulum dosyaları veya yerel veri klasörü okunamadı.";
            }
            catch (UnauthorizedAccessException)
            {
                result.Error = "Lavox ERP için gerekli kullanıcı klasörüne erişilemiyor.";
            }
            catch (System.ComponentModel.Win32Exception)
            {
                result.Error = "Python veya Edge/Chrome başlatılamadı.";
            }
            catch (System.Security.SecurityException)
            {
                result.Error = "Windows güvenlik ilkesi yerel başlatmayı engelledi.";
            }
            catch (InvalidOperationException error)
            {
                result.Error = error.Message;
            }

            if (_splash.IsDisposed || !_splash.IsHandleCreated)
            {
                StopOwnedBackend();
                return;
            }

            _splash.BeginInvoke((MethodInvoker)delegate
            {
                if (!String.IsNullOrEmpty(result.Error))
                {
                    ShowStartupError(result.Error);
                    return;
                }

                _appUrl = result.Url;
                _splash.SetReady();
                _trayIcon.Visible = true;
                _trayIcon.ShowBalloonTip(
                    2500,
                    "LAVOX ELEKTRONİK ERP",
                    "ERP uygulama penceresinde hazır.",
                    ToolTipIcon.Info
                );
                System.Windows.Forms.Timer closeTimer = new System.Windows.Forms.Timer();
                closeTimer.Interval = 650;
                closeTimer.Tick += delegate
                {
                    closeTimer.Stop();
                    closeTimer.Dispose();
                    _splash.Close();
                };
                closeTimer.Start();
            });
        });
    }

    private string StartBackend()
    {
        string backendEntry = Path.Combine(_installRoot, "backend", "main.py");
        if (!File.Exists(backendEntry))
        {
            throw new InvalidOperationException("Lavox ERP kurulum dosyaları eksik.");
        }

        Directory.CreateDirectory(_dataRoot);
        string dataFolder = Path.Combine(_dataRoot, "data");
        Directory.CreateDirectory(dataFolder);

        AppendStartupLog(
            _startupLogPath,
            "[" + DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ") + "] Çalışma kökü: " + _installRoot
        );

        PythonRuntime python = ResolvePythonRuntime();
        if (python == null)
        {
            AppendStartupLog(
                _startupLogPath,
                "[" + DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ") + "] HATA: Python çalışma ortamı bulunamadı."
            );
            throw new InvalidOperationException(
                "Lavox ERP yerel Python çalışma ortamı bulunamadı. " +
                "Uygulamayı yeniden kurun veya kurulum sihirbazını tekrar çalıştırın."
            );
        }

        AppendStartupLog(
            _startupLogPath,
            "[" + DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ") + "] Python çalışma zamanı: " + python.PythonwPath
        );

        string baseUrl = BuildUrl(PreferredPort);
        if (IsLavoxHealthy(PreferredPort) || IsUrlRespondingOk(baseUrl + "/"))
        {
            AppendStartupLog(
                _startupLogPath,
                "[" + DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ") + "] Port 8010 zaten yanıt veriyor; çift sunucu başlatılmıyor."
            );
            return baseUrl;
        }

        if (!IsPortAvailable(PreferredPort))
        {
            throw new InvalidOperationException(
                "ERP arka ucu için 8010 portu kullanımda. Lütfen portu boşaltın ve uygulamayı yeniden başlatın."
            );
        }

        string seedExe = python.PythonPath ?? python.PythonwPath;
        RunSeed(seedExe, dataFolder);

        string launchExe = File.Exists(python.PythonwPath) ? python.PythonwPath : python.PythonPath;
        ProcessStartInfo startInfo = CreateProcessInfo(launchExe);
        startInfo.Arguments =
            "-m uvicorn backend.main:app --host 127.0.0.1 --port 8010 " +
            "--log-level error --no-access-log";
        startInfo.WorkingDirectory = _installRoot;
        startInfo.EnvironmentVariables["LAVOX_DATA_ROOT"] = _dataRoot;
        startInfo.RedirectStandardOutput = true;
        startInfo.RedirectStandardError = true;
        Process process = Process.Start(startInfo);
        if (process == null)
        {
            AppendStartupLog(
                _startupLogPath,
                "[" + DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ") + "] HATA: python işlemi başlatılamadı."
            );
            throw new InvalidOperationException("Yerel ERP arka ucu başlatılamadı.");
        }

        Task.Run(() => RedirectProcessOutput(process, _startupLogPath));

        lock (_processLock)
        {
            _backendProcess = process;
            if (_exiting)
            {
                StopOwnedBackend();
                throw new InvalidOperationException("Başlatma iptal edildi.");
            }
        }

        AppendStartupLog(
            _startupLogPath,
            "[" + DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ") + "] Uvicorn başlatıldı (PID " + process.Id + ")."
        );

        DateTime deadline = DateTime.UtcNow.AddSeconds(35);
        while (DateTime.UtcNow < deadline)
        {
            if (IsLavoxHealthy(PreferredPort))
            {
                AppendStartupLog(
                    _startupLogPath,
                    "[" + DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ") + "] ERP arka ucu hazır (HTTP 200)."
                );
                return baseUrl;
            }
            if (process.HasExited)
            {
                AppendStartupLog(
                    _startupLogPath,
                    "[" + DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ") + "] HATA: python işlemi beklenmedik çıkış yaptı (kod " +
                    process.ExitCode + ")."
                );
                throw new InvalidOperationException(
                    "ERP arka ucu başlatılamadı. Yerel Python çalışma ortamını ve kurulumu doğrulayın."
                );
            }
            Thread.Sleep(250);
        }

        StopOwnedBackend();
        throw new InvalidOperationException(
            "ERP arka ucu zamanında hazır olmadı. Yerel Python çalışma ortamını ve kurulumu doğrulayın."
        );
    }

    private bool IsUrlRespondingOk(string url)
    {
        try
        {
            using (var client = new System.Net.Http.HttpClient { Timeout = TimeSpan.FromSeconds(2) })
            {
                var response = client.GetAsync(url).GetAwaiter().GetResult();
                return response.StatusCode == System.Net.HttpStatusCode.OK;
            }
        }
        catch
        {
            return false;
        }
    }

    private static void AppendStartupLog(string logPath, string message)
    {
        try
        {
            File.AppendAllText(logPath, message + Environment.NewLine);
        }
        catch
        {
        }
    }

    private static void RedirectProcessOutput(Process process, string logPath)
    {
        try
        {
            if (process != null && !process.HasExited)
            {
                string stdout = process.StandardOutput.ReadToEnd();
                if (stdout.Length > 0)
                {
                    AppendStartupLog(logPath, "[uvicorn stdout] " + stdout);
                }
            }
            if (process != null)
            {
                string stderr = process.StandardError.ReadToEnd();
                if (stderr.Length > 0)
                {
                    AppendStartupLog(logPath, "[uvicorn stderr] " + stderr);
                }
            }
        }
        catch
        {
        }
    }

    private void RunSeed(string pythonPath, string workingDirectory)
    {
        ProcessStartInfo seedInfo = CreateProcessInfo(pythonPath);
        seedInfo.Arguments =
            "-c \"from backend.seed_data import seed; seed()\"";
        seedInfo.WorkingDirectory = _installRoot;
        seedInfo.EnvironmentVariables["LAVOX_DATA_ROOT"] = _dataRoot;
        seedInfo.CreateNoWindow = true;

        using (Process seedProcess = Process.Start(seedInfo))
        {
            if (seedProcess == null || !seedProcess.WaitForExit(60000))
            {
                if (seedProcess != null && !seedProcess.HasExited)
                {
                    seedProcess.Kill();
                }
                throw new InvalidOperationException("İlk kullanım veritabanı hazırlanamadı.");
            }

            if (seedProcess.ExitCode != 0)
            {
                throw new InvalidOperationException("İlk kullanım veritabanı hazırlanamadı.");
            }
        }

        if (!Directory.Exists(workingDirectory))
        {
            throw new InvalidOperationException("Kullanıcı veri klasörü oluşturulamadı.");
        }
    }

    private static ProcessStartInfo CreateProcessInfo(string executable)
    {
        ProcessStartInfo info = new ProcessStartInfo();
        info.FileName = executable;
        info.UseShellExecute = false;
        info.CreateNoWindow = true;
        return info;
    }

    private PythonRuntime ResolvePythonRuntime()
    {
        // (a) BaseDirectory\.venv\Scripts\pythonw.exe
        // (b) BaseDirectory\.venv\Scripts\python.exe
        string baseScripts = Path.Combine(_installRoot, ".venv", "Scripts");
        string basePythonw = Path.Combine(baseScripts, "pythonw.exe");
        string basePython = Path.Combine(baseScripts, "python.exe");
        if (File.Exists(basePythonw) || File.Exists(basePython))
        {
            return new PythonRuntime
            {
                PythonPath = File.Exists(basePython) ? basePython : null,
                PythonwPath = File.Exists(basePythonw) ? basePythonw : null
            };
        }

        // (c) C:\Users\MÜSLÜM BAYSÖZ\Desktop\BAYSOZ_YAZILIM\.venv\Scripts\pythonw.exe
        string fallbackScripts = @"C:\Users\MÜSLÜM BAYSÖZ\Desktop\BAYSOZ_YAZILIM\.venv\Scripts";
        string fallbackPythonw = Path.Combine(fallbackScripts, "pythonw.exe");
        string fallbackPython = Path.Combine(fallbackScripts, "python.exe");
        if (File.Exists(fallbackPythonw) || File.Exists(fallbackPython))
        {
            return new PythonRuntime
            {
                PythonPath = File.Exists(fallbackPython) ? fallbackPython : null,
                PythonwPath = File.Exists(fallbackPythonw) ? fallbackPythonw : null
            };
        }

        // (d) System PATH (where.exe pythonw / where.exe python)
        foreach (string command in new[] { "pythonw", "python" })
        {
            string found = LocateExecutableOnPath(command);
            if (found != null)
            {
                return new PythonRuntime
                {
                    PythonPath = command.Equals("python", StringComparison.OrdinalIgnoreCase) ? found : null,
                    PythonwPath = command.Equals("pythonw", StringComparison.OrdinalIgnoreCase) ? found : null
                };
            }
        }

        return null;
    }

    private static string LocateExecutableOnPath(string command)
    {
        try
        {
            using (Process where = Process.Start(
                new ProcessStartInfo
                {
                    FileName = "where.exe",
                    Arguments = command,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true
                }
            ))
            {
                if (where == null || !where.WaitForExit(10000))
                {
                    return null;
                }
                string output = where.StandardOutput.ReadToEnd();
                foreach (string line in output.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries))
                {
                    string trimmed = line.Trim();
                    if (trimmed.Length > 0 && File.Exists(trimmed))
                    {
                        return trimmed;
                    }
                }
            }
        }
        catch
        {
        }
        return null;
    }

    private static bool IsLavoxHealthy(int port)
    {
        HttpWebRequest request = (HttpWebRequest)WebRequest.Create(
            "http://127.0.0.1:" + port.ToString() + "/api/health"
        );
        request.Proxy = null;
        request.Timeout = 600;
        request.ReadWriteTimeout = 600;
        try
        {
            using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
            using (StreamReader reader = new StreamReader(response.GetResponseStream()))
            {
                if (response.StatusCode != HttpStatusCode.OK)
                {
                    return false;
                }
                JavaScriptSerializer serializer = new JavaScriptSerializer();
                Dictionary<string, object> payload =
                    serializer.Deserialize<Dictionary<string, object>>(reader.ReadToEnd());
                return payload != null
                    && payload.ContainsKey("status")
                    && payload.ContainsKey("service")
                    && String.Equals(Convert.ToString(payload["status"]), "ok", StringComparison.Ordinal)
                    && String.Equals(
                        Convert.ToString(payload["service"]),
                        "LAVOX Elektronik ERP",
                        StringComparison.Ordinal
                    );
            }
        }
        catch (WebException)
        {
            return false;
        }
        catch (InvalidOperationException)
        {
            return false;
        }
    }

    private static bool IsPortAvailable(int port)
    {
        TcpListener listener = new TcpListener(System.Net.IPAddress.Loopback, port);
        try
        {
            listener.Start();
            return true;
        }
        catch (SocketException)
        {
            return false;
        }
        finally
        {
            listener.Stop();
        }
    }

    private static int FindFreePort()
    {
        TcpListener listener = new TcpListener(System.Net.IPAddress.Loopback, 0);
        listener.Start();
        int port = ((System.Net.IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop();
        return port;
    }

    private static string BuildUrl(int port)
    {
        return "http://127.0.0.1:" + port.ToString();
    }

    private void OpenAppWindow(string url)
    {
        string browserPath = FindBrowser();
        if (browserPath == null)
        {
            throw new InvalidOperationException(
                "Microsoft Edge veya Google Chrome bulunamadı. Uygulama penceresi açılamadı."
            );
        }

        ProcessStartInfo browserInfo = new ProcessStartInfo();
        browserInfo.FileName = browserPath;
        browserInfo.Arguments = "--app=" + url + " --no-first-run";
        browserInfo.UseShellExecute = false;
        browserInfo.CreateNoWindow = true;
        browserInfo.WorkingDirectory = Path.GetDirectoryName(browserPath);
        using (Process browser = Process.Start(browserInfo))
        {
            if (browser == null)
            {
                throw new InvalidOperationException("ERP uygulama penceresi açılamadı.");
            }
        }
    }

    private static string FindBrowser()
    {
        List<string> candidates = new List<string>();
        string programFilesX86 = Environment.GetFolderPath(
            Environment.SpecialFolder.ProgramFilesX86
        );
        string programFiles = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        string localAppData = Environment.GetFolderPath(
            Environment.SpecialFolder.LocalApplicationData
        );

        AddIfExists(candidates, Path.Combine(programFilesX86, "Microsoft", "Edge", "Application", "msedge.exe"));
        AddIfExists(candidates, Path.Combine(programFiles, "Microsoft", "Edge", "Application", "msedge.exe"));
        AddIfExists(candidates, Path.Combine(localAppData, "Microsoft", "Edge", "Application", "msedge.exe"));
        AddIfExists(candidates, Path.Combine(programFilesX86, "Google", "Chrome", "Application", "chrome.exe"));
        AddIfExists(candidates, Path.Combine(programFiles, "Google", "Chrome", "Application", "chrome.exe"));
        AddIfExists(candidates, Path.Combine(localAppData, "Google", "Chrome", "Application", "chrome.exe"));

        string pathValue = Environment.GetEnvironmentVariable("PATH") ?? String.Empty;
        foreach (string directory in pathValue.Split(Path.PathSeparator))
        {
            string cleanDirectory = directory.Trim().Trim('"');
            if (cleanDirectory.Length == 0 || !Directory.Exists(cleanDirectory))
            {
                continue;
            }
            AddIfExists(candidates, Path.Combine(cleanDirectory, "msedge.exe"));
            AddIfExists(candidates, Path.Combine(cleanDirectory, "chrome.exe"));
        }

        return candidates.Count == 0 ? null : candidates[0];
    }

    private static void AddIfExists(List<string> paths, string candidate)
    {
        if (File.Exists(candidate) && !paths.Contains(candidate))
        {
            paths.Add(candidate);
        }
    }

    private void OpenApplication(object sender, EventArgs e)
    {
        if (!String.IsNullOrEmpty(_appUrl))
        {
            try
            {
                OpenAppWindow(_appUrl);
            }
            catch (InvalidOperationException error)
            {
                MessageBox.Show(error.Message, "LAVOX ELEKTRONİK ERP", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            catch (System.ComponentModel.Win32Exception)
            {
                MessageBox.Show(
                    "Microsoft Edge veya Google Chrome başlatılamadı.",
                    "LAVOX ELEKTRONİK ERP",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
            }
        }
    }

    private void ShowStartupError(string message)
    {
        _splash.Hide();
        MessageBox.Show(
            _splash,
            message,
            "LAVOX ELEKTRONİK ERP",
            MessageBoxButtons.OK,
            MessageBoxIcon.Error
        );
        ExitApplication(null, EventArgs.Empty);
    }

    private void SplashClosed(object sender, FormClosedEventArgs e)
    {
        if (!_trayIcon.Visible)
        {
            ExitApplication(null, EventArgs.Empty);
        }
    }

    private void ExitApplication(object sender, EventArgs e)
    {
        if (_exiting)
        {
            return;
        }
        _exiting = true;
        _trayIcon.Visible = false;
        StopOwnedBackend();
        _trayIcon.Dispose();
        _splash.Dispose();
        ExitThread();
    }

    private void StopOwnedBackend()
    {
        Process process;
        lock (_processLock)
        {
            process = _backendProcess;
        }

        if (process == null)
        {
            return;
        }

        try
        {
            if (!process.HasExited)
            {
                process.CloseMainWindow();
                if (!process.WaitForExit(2500))
                {
                    process.Kill();
                    process.WaitForExit(2500);
                }
            }
        }
        catch (InvalidOperationException)
        {
        }
        catch (System.ComponentModel.Win32Exception)
        {
        }
        finally
        {
            process.Dispose();
        }
    }

    private sealed class PythonRuntime
    {
        public string PythonPath;
        public string PythonwPath;
    }
}

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new LauncherContext());
    }
}
