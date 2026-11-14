using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Windows.Forms;

internal sealed class InstallRequest
{
    public string TargetDirectory;
    public bool CreateDesktopShortcut;
}

internal sealed class InstallResult
{
    public string TargetDirectory;
    public bool CreateDesktopShortcut;
}

internal sealed class InstallerWizard : Form
{
    private const string ArchiveResourceName = "Lavox.ERP.ProjectArchive.zip";
    private const string LauncherResourceName = "Lavox.ERP.Launcher.exe";
    private readonly Panel _content;
    private readonly Panel _footer;
    private readonly Button _backButton;
    private readonly Button _nextButton;
    private readonly Button _cancelButton;
    private readonly BackgroundWorker _worker;
    private int _step = 1;
    private TextBox _targetPath;
    private CheckBox _desktopShortcut;
    private CheckBox _licenseAccepted;
    private CheckBox _launchAfterInstall;
    private ProgressBar _progress;
    private Label _progressStatus;

    public InstallerWizard()
    {
        Text = "LAVOX ELEKTRONİK ERP Kurulum Sihirbazı";
        Name = "InstallerWizard";
        AccessibleName = "LAVOX ELEKTRONİK ERP Kurulum Sihirbazı";
        StartPosition = FormStartPosition.CenterScreen;
        ClientSize = new Size(800, 540);
        MinimumSize = new Size(800, 540);
        MaximumSize = new Size(800, 540);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = true;
        BackColor = Color.White;
        Icon appIcon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        if (appIcon != null)
        {
            Icon = appIcon;
        }

        Panel header = new Panel();
        header.Dock = DockStyle.Top;
        header.Height = 88;
        header.BackColor = Color.FromArgb(21, 40, 68);
        Controls.Add(header);

        Label brand = new Label();
        brand.AutoSize = false;
        brand.Location = new Point(32, 19);
        brand.Size = new Size(720, 30);
        brand.ForeColor = Color.White;
        brand.Font = new Font("Segoe UI", 16, FontStyle.Bold);
        brand.Text = "LAVOX ELEKTRONİK";
        header.Controls.Add(brand);

        Label subtitle = new Label();
        subtitle.AutoSize = false;
        subtitle.Location = new Point(34, 52);
        subtitle.Size = new Size(720, 21);
        subtitle.ForeColor = Color.FromArgb(189, 205, 230);
        subtitle.Font = new Font("Segoe UI", 9, FontStyle.Regular);
        subtitle.Text = "Kurumsal ERP v2.0  |  BAYSÖZ YAZILIM";
        header.Controls.Add(subtitle);

        _content = new Panel();
        _content.Dock = DockStyle.Fill;
        _content.Padding = new Padding(34, 24, 34, 16);
        _content.BackColor = Color.White;
        Controls.Add(_content);

        _footer = new Panel();
        _footer.Dock = DockStyle.Bottom;
        _footer.Height = 64;
        _footer.BackColor = Color.FromArgb(247, 249, 252);
        Controls.Add(_footer);

        _backButton = new Button();
        _backButton.Name = "BackButton";
        _backButton.AccessibleName = "Geri";
        _backButton.Text = "Geri";
        _backButton.Size = new Size(94, 32);
        _backButton.Location = new Point(476, 16);
        _backButton.Click += Back;
        _footer.Controls.Add(_backButton);

        _nextButton = new Button();
        _nextButton.Name = "NextButton";
        _nextButton.AccessibleName = "İleri";
        _nextButton.Text = "İleri";
        _nextButton.Size = new Size(112, 32);
        _nextButton.Location = new Point(578, 16);
        _nextButton.BackColor = Color.FromArgb(54, 96, 180);
        _nextButton.ForeColor = Color.White;
        _nextButton.FlatStyle = FlatStyle.Flat;
        _nextButton.Click += Next;
        _footer.Controls.Add(_nextButton);

        _cancelButton = new Button();
        _cancelButton.Name = "CancelButton";
        _cancelButton.AccessibleName = "İptal";
        _cancelButton.Text = "İptal";
        _cancelButton.Size = new Size(76, 32);
        _cancelButton.Location = new Point(700, 16);
        _cancelButton.Click += CancelInstall;
        _footer.Controls.Add(_cancelButton);

        _worker = new BackgroundWorker();
        _worker.WorkerReportsProgress = true;
        _worker.DoWork += InstallFiles;
        _worker.ProgressChanged += InstallationProgressChanged;
        _worker.RunWorkerCompleted += InstallationCompleted;

        FormClosing += PreventCloseDuringInstall;
        ShowStep();
    }

    private void ShowStep()
    {
        _content.Controls.Clear();
        _backButton.Enabled = _step > 1 && _step < 3;
        _nextButton.Enabled = true;
        _cancelButton.Enabled = true;

        if (_step == 1)
        {
            AddHeading("Hoş geldiniz");
            AddBody(
                "LAVOX ELEKTRONİK Kurumsal ERP v2.0 Kurulum Sihirbazı",
                34,
                92,
                700,
                32,
                15,
                true
            );
            AddBody(
                "BAYSÖZ YAZILIM tarafından hazırlanan kurulum, ERP dosyalarını kullanıcı profilinizdeki yerel uygulama klasörüne kopyalar. Sistem dosyaları veya mevcut kullanıcı verileri silinmez.",
                34,
                145,
                700,
                72,
                10,
                false
            );
            AddBody(
                "Devam etmek için İleri'yi seçin.",
                34,
                246,
                700,
                24,
                10,
                false
            );
            _backButton.Enabled = false;
            _nextButton.Text = "İleri";
            AcceptButton = _nextButton;
            return;
        }

        if (_step == 2)
        {
            AddHeading("Lisans ve kurulum konumu");
            AddBody(
                "Kurulum bilgisi: Paket, mevcut lisans koşullarına tabidir ve ayrı bir yazılım lisansı vermez.",
                34,
                78,
                700,
                42,
                9,
                false
            );

            Label licenseLabel = AddBody(
                "Kurulum klasörü",
                34,
                132,
                700,
                22,
                9,
                true
            );
            licenseLabel.Name = "InstallPathLabel";

            _targetPath = new TextBox();
            _targetPath.Name = "InstallPath";
            _targetPath.AccessibleName = "Kurulum klasörü";
            _targetPath.Location = new Point(34, 158);
            _targetPath.Size = new Size(700, 25);
            _targetPath.Text = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Lavox_ERP"
            );
            _content.Controls.Add(_targetPath);

            _desktopShortcut = new CheckBox();
            _desktopShortcut.Name = "DesktopShortcut";
            _desktopShortcut.AccessibleName = "Masaüstüne kısayol oluştur";
            _desktopShortcut.AutoSize = true;
            _desktopShortcut.Location = new Point(34, 197);
            _desktopShortcut.Text = "Masaüstüne kısayol oluştur";
            _desktopShortcut.Checked = true;
            _content.Controls.Add(_desktopShortcut);

            _licenseAccepted = new CheckBox();
            _licenseAccepted.Name = "LicenseAccepted";
            _licenseAccepted.AccessibleName = "Kurulum bilgilerini okudum";
            _licenseAccepted.AutoSize = true;
            _licenseAccepted.Location = new Point(34, 230);
            _licenseAccepted.Text = "Kurulum bilgisini okudum ve devam etmeyi kabul ediyorum.";
            _licenseAccepted.CheckedChanged += LicenseAcceptedChanged;
            _content.Controls.Add(_licenseAccepted);

            AddBody(
                "Başlatmak için Python 3, FastAPI, Uvicorn ve Microsoft Edge veya Google Chrome gerekir. Sihirbaz, kurulum sırasında yerel bir Python sanal ortamı (.venv) oluşturur ve gerekli Python paketlerini (fastapi, uvicorn, pydantic) sessizce yükler.",
                34,
                276,
                700,
                55,
                9,
                false
            );
            _nextButton.Text = "Yükle";
            _nextButton.Enabled = false;
            AcceptButton = _nextButton;
            return;
        }

        if (_step == 3)
        {
            AddHeading("Kurulum sürüyor");
            _progressStatus = AddBody(
                "Lavox ERP dosyaları hazırlanıyor...",
                34,
                93,
                700,
                28,
                10,
                false
            );
            _progressStatus.Name = "ProgressStatus";

            _progress = new ProgressBar();
            _progress.Name = "InstallationProgress";
            _progress.AccessibleName = "Kurulum ilerlemesi";
            _progress.Location = new Point(34, 132);
            _progress.Size = new Size(700, 20);
            _progress.Minimum = 0;
            _progress.Maximum = 100;
            _progress.Style = ProgressBarStyle.Continuous;
            _content.Controls.Add(_progress);

            AddBody(
                "Dosyalar kullanıcı profilindeki kurulum klasörüne kopyalanıyor. İşlem tamamlanana kadar bu pencereyi kapatmayın.",
                34,
                171,
                700,
                50,
                9,
                false
            );
            _backButton.Enabled = false;
            _nextButton.Enabled = false;
            _nextButton.Text = "Yükleniyor...";
            _cancelButton.Enabled = false;
            AcceptButton = null;
            return;
        }

        AddHeading("Kurulum tamamlandı");
        AddBody(
            "LAVOX ELEKTRONİK Kurumsal ERP v2.0 başarıyla kuruldu.",
            34,
            98,
            700,
            30,
            12,
            true
        );
        AddBody(
            "Uygulama, başlatma sırasında yerel Python çalışma zamanını ve ERP arka ucunu denetler.",
            34,
            145,
            700,
            45,
            9,
            false
        );
        _launchAfterInstall = new CheckBox();
        _launchAfterInstall.Name = "LaunchAfterInstall";
        _launchAfterInstall.AccessibleName = "Lavox Elektronik ERP'yi şimdi başlat";
        _launchAfterInstall.AutoSize = true;
        _launchAfterInstall.Location = new Point(34, 207);
        _launchAfterInstall.Text = "Lavox Elektronik ERP'yi şimdi başlat";
        _launchAfterInstall.Checked = true;
        _content.Controls.Add(_launchAfterInstall);
        _backButton.Enabled = false;
        _nextButton.Text = "Bitir";
        _cancelButton.Enabled = false;
        AcceptButton = _nextButton;
    }

    private void AddHeading(string text)
    {
        Label heading = new Label();
        heading.AutoSize = false;
        heading.Location = new Point(34, 22);
        heading.Size = new Size(700, 34);
        heading.ForeColor = Color.FromArgb(31, 47, 70);
        heading.Font = new Font("Segoe UI", 17, FontStyle.Bold);
        heading.Text = text;
        _content.Controls.Add(heading);
    }

    private Label AddBody(
        string text,
        int x,
        int y,
        int width,
        int height,
        float fontSize,
        bool bold
    )
    {
        Label label = new Label();
        label.AutoSize = false;
        label.Location = new Point(x, y);
        label.Size = new Size(width, height);
        label.ForeColor = Color.FromArgb(63, 76, 97);
        label.Font = new Font("Segoe UI", fontSize, bold ? FontStyle.Bold : FontStyle.Regular);
        label.Text = text;
        _content.Controls.Add(label);
        return label;
    }

    private void LicenseAcceptedChanged(object sender, EventArgs e)
    {
        if (_step == 2)
        {
            _nextButton.Enabled = _licenseAccepted.Checked;
        }
    }

    private void Next(object sender, EventArgs e)
    {
        if (_step == 1)
        {
            _step = 2;
            ShowStep();
            return;
        }

        if (_step == 2)
        {
            if (!_licenseAccepted.Checked)
            {
                return;
            }

            string targetDirectory;
            try
            {
                targetDirectory = ValidateTargetDirectory(_targetPath.Text);
            }
            catch (ArgumentException error)
            {
                MessageBox.Show(error.Message, Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                _targetPath.Focus();
                return;
            }

            InstallRequest request = new InstallRequest();
            request.TargetDirectory = targetDirectory;
            request.CreateDesktopShortcut = _desktopShortcut.Checked;
            _step = 3;
            ShowStep();
            _worker.RunWorkerAsync(request);
            return;
        }

        if (_step == 4)
        {
            if (_launchAfterInstall != null && _launchAfterInstall.Checked)
            {
                try
                {
                    ProcessStartInfo launchInfo = new ProcessStartInfo();
                    launchInfo.FileName = Path.Combine(
                        GetInstallDirectoryFromResult(),
                        "Lavox_ERP.exe"
                    );
                    launchInfo.UseShellExecute = true;
                    Process.Start(launchInfo);
                }
                catch (System.ComponentModel.Win32Exception)
                {
                    MessageBox.Show(
                        "Kurulan ERP başlatılamadı. Kurulum klasörünü ve Python çalışma zamanını doğrulayın.",
                        Text,
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error
                    );
                }
                catch (FileNotFoundException)
                {
                    MessageBox.Show(
                        "Kurulan ERP başlatıcısı bulunamadı.",
                        Text,
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error
                    );
                }
            }
            Close();
        }
    }

    private string _installedDirectory;

    private string GetInstallDirectoryFromResult()
    {
        return _installedDirectory;
    }

    private static string ValidateTargetDirectory(string value)
    {
        if (String.IsNullOrWhiteSpace(value))
        {
            throw new ArgumentException("Kurulum klasörü boş bırakılamaz.");
        }

        string fullPath;
        try
        {
            fullPath = Path.GetFullPath(value.Trim());
        }
        catch (Exception error)
        {
            if (error is ArgumentException || error is NotSupportedException || error is PathTooLongException)
            {
                throw new ArgumentException("Geçerli bir kurulum klasörü girin.");
            }
            throw;
        }

        string root = Path.GetPathRoot(fullPath);
        string normalized = fullPath.TrimEnd(
            Path.DirectorySeparatorChar,
            Path.AltDirectorySeparatorChar
        );
        if (String.IsNullOrEmpty(normalized)
            || String.Equals(normalized, root.TrimEnd(
                Path.DirectorySeparatorChar,
                Path.AltDirectorySeparatorChar
            ), StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException("Windows sürücüsünün kök klasörü kurulum hedefi olamaz.");
        }

        return normalized;
    }

    private void Back(object sender, EventArgs e)
    {
        if (_step > 1 && _step < 3)
        {
            _step -= 1;
            ShowStep();
        }
    }

    private void CancelInstall(object sender, EventArgs e)
    {
        Close();
    }

    private void PreventCloseDuringInstall(object sender, FormClosingEventArgs e)
    {
        if (_worker.IsBusy)
        {
            e.Cancel = true;
        }
    }

    private void InstallFiles(object sender, DoWorkEventArgs e)
    {
        InstallRequest request = (InstallRequest)e.Argument;
        Directory.CreateDirectory(request.TargetDirectory);
        ExtractProjectArchive(request.TargetDirectory, (BackgroundWorker)sender);
        EnsurePythonRuntime(request.TargetDirectory, (BackgroundWorker)sender);
        InstallNativeLauncher(request.TargetDirectory);

        if (request.CreateDesktopShortcut)
        {
            CreateDesktopShortcut(request.TargetDirectory);
        }

        InstallResult result = new InstallResult();
        result.TargetDirectory = request.TargetDirectory;
        result.CreateDesktopShortcut = request.CreateDesktopShortcut;
        e.Result = result;
    }

    private void EnsurePythonRuntime(string targetDirectory, BackgroundWorker worker)
    {
        string venvRoot = Path.Combine(targetDirectory, ".venv");
        string scriptsDir = Path.Combine(venvRoot, "Scripts");
        string pythonExe = Path.Combine(scriptsDir, "python.exe");
        string pythonwExe = Path.Combine(scriptsDir, "pythonw.exe");

        worker.ReportProgress(76, "Python çalışma ortamı denetleniyor...");
        if (File.Exists(pythonwExe) && File.Exists(pythonExe))
        {
            return;
        }

        worker.ReportProgress(78, "Sistem Python çalışma zamanı aranıyor...");
        string systemPython = LocateSystemPython();
        if (systemPython == null)
        {
            worker.ReportProgress(80, "Python sistemde yok. Yerleşik Python paketi indiriliyor...");
            systemPython = DownloadPortablePython(targetDirectory, worker);
        }
        if (systemPython == null)
        {
            throw new InvalidOperationException(
                "Python 3 çalışma zamanını bu bilgisayarda bulunamadı. " +
                "Lütfen Python 3.10 veya üzerini yükleyin ve kurulumu tekrar deneyin."
            );
        }

        if (!Directory.Exists(venvRoot))
        {
            worker.ReportProgress(82, "Sanal Python ortamı (.venv) oluşturuluyor...");
            RunProcess(
                systemPython,
                "-m venv \"" + venvRoot + "\"",
                targetDirectory,
                worker,
                120000
            );
        }

        if (!File.Exists(pythonwExe) || !File.Exists(pythonExe))
        {
            throw new InvalidOperationException(
                "Sanal Python ortamı oluşturulamadı. Kurulum klasörü izinlerini kontrol edin."
            );
        }

        string requirementsFile = Path.Combine(targetDirectory, "requirements-runtime.txt");
        worker.ReportProgress(88, "ERP Python paketleri yükleniyor (requirements-runtime.txt)...");
        if (!File.Exists(requirementsFile))
        {
            throw new InvalidOperationException(
                "requirements-runtime.txt kurulum dosyasında eksik. Kurulumu tekrar deneyin."
            );
        }
        string pipExe = Path.Combine(scriptsDir, "pip.exe");
        if (!File.Exists(pipExe))
        {
            throw new InvalidOperationException(
                "pip çalıştırıcısı sanal ortamda bulunamadı. Kurulumu tekrar deneyin."
            );
        }
        RunProcess(
            pipExe,
            "install -r \"" + requirementsFile + "\"",
            targetDirectory,
            worker,
            600000
        );

        worker.ReportProgress(95, "Python çalışma ortamı hazır.");
    }

    private string LocateSystemPython()
    {
        foreach (string command in new[] { "py", "python" })
        {
            try
            {
                using (Process check = Process.Start(
                    new ProcessStartInfo
                    {
                        FileName = command,
                        Arguments = "--version",
                        UseShellExecute = false,
                        CreateNoWindow = true,
                        RedirectStandardOutput = true,
                        RedirectStandardError = true
                    }
                ))
                {
                    if (check != null && check.WaitForExit(10000) && check.ExitCode == 0)
                    {
                        return command;
                    }
                }
            }
            catch (System.ComponentModel.Win32Exception)
            {
            }
            catch (InvalidOperationException)
            {
            }
        }

        string[] commonPaths = new[]
        {
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "Python312", "python.exe"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "Python311", "python.exe"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), "Python312", "python.exe"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), "Python311", "python.exe")
        };
        foreach (string candidate in commonPaths)
        {
            if (File.Exists(candidate))
            {
                return candidate;
            }
        }
        return null;
    }

    private string DownloadPortablePython(string targetDirectory, BackgroundWorker worker)
    {
        string embedRoot = Path.Combine(targetDirectory, ".python-embed");
        string embedExe = Path.Combine(embedRoot, "python.exe");
        if (File.Exists(embedExe))
        {
            return embedExe;
        }

        const string url = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip";
        string zipPath = Path.Combine(Path.GetTempPath(), "lavox-python-embed.zip");

        try
        {
            worker.ReportProgress(82, "Yerleşik Python paketi indiriliyor (bu adım birkaç dakika sürebilir)...");
            using (WebClient client = new WebClient())
            {
                client.DownloadFile(url, zipPath);
            }

            worker.ReportProgress(85, "Yerleşik Python paketi çıkartılıyor...");
            Directory.CreateDirectory(embedRoot);
            ZipFile.ExtractToDirectory(zipPath, embedRoot);

            if (!File.Exists(embedExe))
            {
                return null;
            }

            try { File.Delete(zipPath); } catch { }
            return embedExe;
        }
        catch
        {
            return null;
        }
    }

    private static void RunProcess(string fileName, string arguments, string workingDirectory, BackgroundWorker worker, int timeoutMs)
    {
        using (Process process = Process.Start(
            new ProcessStartInfo
            {
                FileName = fileName,
                Arguments = arguments,
                UseShellExecute = false,
                CreateNoWindow = true,
                WorkingDirectory = workingDirectory,
                RedirectStandardOutput = true,
                RedirectStandardError = true
            }
        ))
        {
            if (process == null)
            {
                throw new InvalidOperationException("İşlem başlatılamadı: " + fileName);
            }
            if (!process.WaitForExit(timeoutMs))
            {
                try { process.Kill(); } catch { }
                throw new InvalidOperationException("İşlem zaman aşımına uğradı: " + fileName);
            }
            if (process.ExitCode != 0)
            {
                throw new InvalidOperationException(
                    "İşlem başarısız oldu (çıkış kodu " + process.ExitCode + "): " + fileName
                );
            }
        }
    }

    private static void ExtractProjectArchive(string targetDirectory, BackgroundWorker worker)
    {
        Assembly assembly = Assembly.GetExecutingAssembly();
        using (Stream archiveStream = assembly.GetManifestResourceStream(ArchiveResourceName))
        {
            if (archiveStream == null)
            {
                throw new InvalidDataException("Kurulum paketinde ERP dosyaları bulunamadı.");
            }

            using (ZipArchive archive = new ZipArchive(archiveStream, ZipArchiveMode.Read, false))
            {
                string destinationRoot = Path.GetFullPath(targetDirectory).TrimEnd(
                    Path.DirectorySeparatorChar,
                    Path.AltDirectorySeparatorChar
                ) + Path.DirectorySeparatorChar;
                int totalFiles = 0;
                foreach (ZipArchiveEntry entry in archive.Entries)
                {
                    if (!String.IsNullOrEmpty(entry.Name))
                    {
                        totalFiles += 1;
                    }
                }

                int processed = 0;
                foreach (ZipArchiveEntry entry in archive.Entries)
                {
                    string relativePath = entry.FullName.Replace(
                        '/',
                        Path.DirectorySeparatorChar
                    );
                    string destinationPath = Path.GetFullPath(
                        Path.Combine(destinationRoot, relativePath)
                    );
                    if (!destinationPath.StartsWith(
                        destinationRoot,
                        StringComparison.OrdinalIgnoreCase
                    ))
                    {
                        throw new InvalidDataException("Kurulum paketinde geçersiz bir dosya yolu var.");
                    }

                    if (String.IsNullOrEmpty(entry.Name))
                    {
                        Directory.CreateDirectory(destinationPath);
                        continue;
                    }

                    string parent = Path.GetDirectoryName(destinationPath);
                    if (!Directory.Exists(parent))
                    {
                        Directory.CreateDirectory(parent);
                    }

                    using (Stream input = entry.Open())
                    using (FileStream output = new FileStream(
                        destinationPath,
                        FileMode.Create,
                        FileAccess.Write,
                        FileShare.None
                    ))
                    {
                        input.CopyTo(output);
                    }

                    processed += 1;
                    int percentage = totalFiles == 0
                        ? 75
                        : 10 + (processed * 75 / totalFiles);
                    worker.ReportProgress(
                        percentage,
                        "Dosya kopyalandı: " + entry.Name
                    );
                }
            }
        }
    }

    private static void InstallNativeLauncher(string targetDirectory)
    {
        string launcherPath = Path.Combine(targetDirectory, "Lavox_ERP.exe");
        string temporaryPath = launcherPath + ".new";
        Assembly assembly = Assembly.GetExecutingAssembly();

        using (Stream launcherStream = assembly.GetManifestResourceStream(LauncherResourceName))
        {
            if (launcherStream == null)
            {
                throw new InvalidDataException("Kurulum paketinde yerel başlatıcı bulunamadı.");
            }

            using (FileStream output = new FileStream(
                temporaryPath,
                FileMode.Create,
                FileAccess.Write,
                FileShare.None
            ))
            {
                launcherStream.CopyTo(output);
            }
        }

        if (File.Exists(launcherPath))
        {
            File.Replace(temporaryPath, launcherPath, null);
        }
        else
        {
            File.Move(temporaryPath, launcherPath);
        }
    }

    private static void CreateDesktopShortcut(string targetDirectory)
    {
        string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        string shortcutPath = Path.Combine(desktop, "Lavox Elektronik ERP.lnk");
        string launcherPath = Path.Combine(targetDirectory, "Lavox_ERP.exe");
        Type shellType = Type.GetTypeFromProgID("WScript.Shell");
        if (shellType == null)
        {
            throw new InvalidOperationException("Windows masaüstü kısayolu oluşturulamadı.");
        }

        object shell = null;
        object shortcut = null;
        try
        {
            shell = Activator.CreateInstance(shellType);
            shortcut = shellType.InvokeMember(
                "CreateShortcut",
                BindingFlags.InvokeMethod,
                null,
                shell,
                new object[] { shortcutPath }
            );
            Type shortcutType = shortcut.GetType();
            shortcutType.InvokeMember(
                "TargetPath",
                BindingFlags.SetProperty,
                null,
                shortcut,
                new object[] { launcherPath }
            );
            shortcutType.InvokeMember(
                "WorkingDirectory",
                BindingFlags.SetProperty,
                null,
                shortcut,
                new object[] { targetDirectory }
            );
            shortcutType.InvokeMember(
                "IconLocation",
                BindingFlags.SetProperty,
                null,
                shortcut,
                new object[] { launcherPath + ",0" }
            );
            shortcutType.InvokeMember(
                "Description",
                BindingFlags.SetProperty,
                null,
                shortcut,
                new object[] { "LAVOX ELEKTRONİK Kurumsal ERP" }
            );
            shortcutType.InvokeMember("Save", BindingFlags.InvokeMethod, null, shortcut, null);
        }
        finally
        {
            if (shortcut != null && Marshal.IsComObject(shortcut))
            {
                Marshal.FinalReleaseComObject(shortcut);
            }
            if (shell != null && Marshal.IsComObject(shell))
            {
                Marshal.FinalReleaseComObject(shell);
            }
        }
    }

    private void InstallationProgressChanged(object sender, ProgressChangedEventArgs e)
    {
        if (_progress != null)
        {
            _progress.Value = Math.Max(0, Math.Min(100, e.ProgressPercentage));
        }
        if (_progressStatus != null && e.UserState != null)
        {
            _progressStatus.Text = Convert.ToString(e.UserState);
        }
    }

    private void InstallationCompleted(object sender, RunWorkerCompletedEventArgs e)
    {
        if (e.Error != null)
        {
            _nextButton.Enabled = false;
            _nextButton.Text = "Kurulum başarısız";
            _cancelButton.Enabled = true;
            if (_progressStatus != null)
            {
                _progressStatus.Text = "Kurulum tamamlanamadı.";
            }
            MessageBox.Show(
                "Kurulum tamamlanamadı. Hedef klasör izinlerini ve kullanılabilir disk alanını kontrol edin.",
                Text,
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return;
        }

        InstallResult result = (InstallResult)e.Result;
        _installedDirectory = result.TargetDirectory;
        _progress.Value = 100;
        _step = 4;
        ShowStep();
    }
}

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new InstallerWizard());
    }
}
