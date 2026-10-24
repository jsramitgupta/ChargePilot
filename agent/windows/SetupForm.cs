using System.Diagnostics;
using System.Net.Http.Headers;
using System.Text.Json;
using ChargePilotAgent.Core;

namespace ChargePilotAgent;

internal sealed class SetupForm : Form
{
    private static readonly Color Ink = ColorTranslator.FromHtml("#193833");
    private static readonly Color Forest = ColorTranslator.FromHtml("#173F39");
    private static readonly Color Leaf = ColorTranslator.FromHtml("#397A61");
    private static readonly Color Paper = ColorTranslator.FromHtml("#EEF3F0");
    private static readonly Color Line = ColorTranslator.FromHtml("#D7E2DC");
    private readonly ConfigurationStore _configurationStore = new();
    private readonly Label _serverUrl = new()
    {
        AutoSize = true,
        ForeColor = Ink,
        Text = "https://api-chargepilot.endusercompute.in",
    };
    private readonly ComboBox _deviceClass = new() { Dock = DockStyle.Left, DropDownStyle = ComboBoxStyle.DropDownList, Width = 180 };
    private readonly NumericUpDown _interval = new() { Minimum = 1, Maximum = 60, Value = 5, Width = 180 };
    private readonly TextBox _enrollmentToken = new() { Dock = DockStyle.Fill, UseSystemPasswordChar = true };
    private readonly Label _serviceStatus = new() { AutoSize = true, Font = new Font("Segoe UI", 11, FontStyle.Bold), ForeColor = Forest };
    private readonly Label _versionStatus = new() { AutoSize = true, ForeColor = ColorTranslator.FromHtml("#71827B") };
    private readonly Label _message = new() { AutoSize = true, MaximumSize = new Size(660, 0) };
    private readonly Button _saveButton = new() { Text = "Save and start service", AutoSize = true, BackColor = Leaf, ForeColor = Color.White, FlatStyle = FlatStyle.Flat };
    private readonly Button _updateButton = new() { Text = "Update agent", AutoSize = true };
    private readonly Button _startButton = new() { Text = "Start", AutoSize = true };
    private readonly Button _stopButton = new() { Text = "Stop", AutoSize = true };
    private readonly Button _deregisterButton = new() { Text = "Deregister device", AutoSize = true };
    private readonly Button _uninstallButton = new() { Text = "Uninstall service", AutoSize = true };
    private readonly string _agentVersion;
    private AgentOptions? _existingOptions;

    public SetupForm(string agentVersion, string? serverUrl = null)
    {
        _agentVersion = agentVersion;
        Text = "ChargePilot Agent";
        StartPosition = FormStartPosition.CenterScreen;
        MinimumSize = new Size(680, 610);
        Size = new Size(760, 670);
        BackColor = Paper;
        ForeColor = Ink;
        Font = new Font("Segoe UI", 10);

        _deviceClass.Items.AddRange(["Laptop", "Desktop"]);
        _deviceClass.SelectedIndex = 0;

        var page = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            BackColor = Color.White,
            Padding = new Padding(28),
            ColumnCount = 1,
            RowCount = 5,
        };
        page.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        page.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        page.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        page.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        page.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        Controls.Add(page);

        var title = new Label
        {
            Text = "ChargePilot Agent",
            AutoSize = true,
            Font = new Font("Segoe UI", 22, FontStyle.Bold),
            ForeColor = Forest,
            Margin = new Padding(0, 0, 0, 4),
        };
        page.Controls.Add(title, 0, 0);
        page.Controls.Add(new Label
        {
            Text = "Connect this Windows device and manage its background telemetry service.",
            AutoSize = true,
            ForeColor = Ink,
            Margin = new Padding(0, 0, 0, 20),
        }, 0, 1);

        var statusLine = new FlowLayoutPanel
        {
            AutoSize = true,
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.LeftToRight,
            Margin = new Padding(0, 0, 0, 18),
        };
        statusLine.Controls.Add(new Label
        {
            Text = "Service",
            AutoSize = true,
            ForeColor = Ink,
            Margin = new Padding(0, 4, 10, 0),
        });
        statusLine.Controls.Add(_serviceStatus);
        _versionStatus.Margin = new Padding(18, 4, 0, 0);
        statusLine.Controls.Add(_versionStatus);
        page.Controls.Add(statusLine, 0, 2);

        var fields = new TableLayoutPanel
        {
            AutoSize = true,
            Dock = DockStyle.Top,
            ColumnCount = 2,
            RowCount = 4,
            Margin = new Padding(0, 0, 0, 16),
        };
        fields.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 174));
        fields.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        for (var index = 0; index < 4; index++)
        {
            fields.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        }
        AddField(fields, 0, "ChargePilot server", _serverUrl);
        AddField(fields, 1, "Device class", _deviceClass);
        AddField(fields, 2, "Report every (minutes)", _interval);
        AddField(fields, 3, "Enrollment token", _enrollmentToken);

        var fieldsAndNote = new FlowLayoutPanel
        {
            AutoSize = true,
            Dock = DockStyle.Top,
            FlowDirection = FlowDirection.TopDown,
            WrapContents = false,
        };
        fieldsAndNote.Controls.Add(fields);
        fieldsAndNote.Controls.Add(new Label
        {
            Text = "The PC name is used automatically. Device serial numbers are not collected. Leave the token blank to keep the current enrollment.",
            AutoSize = true,
            MaximumSize = new Size(660, 0),
            ForeColor = ColorTranslator.FromHtml("#71827B"),
            Margin = new Padding(0, 0, 0, 12),
        });
        page.Controls.Add(fieldsAndNote, 0, 3);

        var footer = new FlowLayoutPanel
        {
            AutoSize = true,
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.TopDown,
            WrapContents = false,
            Margin = new Padding(0, 16, 0, 0),
        };
        var actions = new FlowLayoutPanel
        {
            AutoSize = true,
            FlowDirection = FlowDirection.LeftToRight,
            WrapContents = true,
        };
        _saveButton.FlatAppearance.BorderSize = 0;
        _saveButton.Padding = new Padding(12, 7, 12, 7);
        _saveButton.Click += async (_, _) => await SaveAndStartAsync();
        _updateButton.Click += async (_, _) => await UpdateAgentAsync();
        _startButton.Click += (_, _) => RunServiceAction(ServiceManager.Start);
        _stopButton.Click += (_, _) => RunServiceAction(ServiceManager.Stop);
        _deregisterButton.Click += async (_, _) => await DeregisterAsync();
        _uninstallButton.Click += (_, _) => UninstallService();
        actions.Controls.AddRange([_saveButton, _updateButton, _startButton, _stopButton, _deregisterButton, _uninstallButton]);
        footer.Controls.Add(actions);
        _message.Margin = new Padding(0, 10, 0, 0);
        footer.Controls.Add(_message);
        footer.Controls.Add(new Label
        {
            Text = "The service runs without a logged-in user. Its credential is protected with Windows machine encryption and an administrator-only file permission.",
            AutoSize = true,
            MaximumSize = new Size(660, 0),
            ForeColor = ColorTranslator.FromHtml("#71827B"),
            Margin = new Padding(0, 8, 0, 0),
        });
        page.Controls.Add(footer, 0, 4);

        LoadConfiguration(serverUrl);
        RefreshServiceStatus();
        var isAdmin = ServiceManager.IsAdministrator();
        _saveButton.Enabled = isAdmin;
        _versionStatus.Text = $"Version {_agentVersion}";
        _updateButton.Enabled = isAdmin && _existingOptions is not null && _serviceStatus.Text != "Not installed";
        _startButton.Enabled = isAdmin;
        _stopButton.Enabled = isAdmin;
        _deregisterButton.Enabled = isAdmin && _existingOptions is not null;
        _uninstallButton.Enabled = isAdmin && _serviceStatus.Text != "Not installed";
        if (!isAdmin)
        {
            ShowMessage("Close this window and reopen ChargePilot Agent with Run as administrator to install or change the service.", isError: true);
        }
    }

    private static void AddField(TableLayoutPanel panel, int row, string label, Control control)
    {
        panel.Controls.Add(new Label
        {
            Text = label,
            AutoSize = true,
            Anchor = AnchorStyles.Left,
            ForeColor = Ink,
            Margin = new Padding(0, 9, 12, 9),
        }, 0, row);
        control.Margin = new Padding(0, 4, 0, 4);
        if (control is TextBox textBox)
        {
            textBox.BorderStyle = BorderStyle.FixedSingle;
            textBox.MinimumSize = new Size(0, 30);
        }
        panel.Controls.Add(control, 1, row);
    }

    private void LoadConfiguration(string? serverUrl)
    {
        try
        {
            _existingOptions = _configurationStore.Load()
                ?? _configurationStore.ImportLegacyUserConfiguration();
        }
        catch (Exception exception)
        {
            ShowMessage(exception.Message, isError: true);
        }

        _serverUrl.Text = serverUrl
            ?? _existingOptions?.ServerUri.ToString()
            ?? Program.DefaultServerUrl;
        _deviceClass.SelectedItem = _existingOptions?.DeviceClass == "desktop" ? "Desktop" : "Laptop";
        _interval.Value = _existingOptions?.IntervalMinutes ?? 5;
    }

    private async Task SaveAndStartAsync()
    {
        SetBusy(true);
        try
        {
            var serverUri = new Uri(_serverUrl.Text);
            var deviceClass = _deviceClass.SelectedItem?.ToString()?.ToLowerInvariant()
                ?? throw new ArgumentException("Select a device class.");
            var deviceName = Environment.MachineName;
            var enrollmentCode = _enrollmentToken.Text.Trim();
            AgentOptions options;

            if (enrollmentCode.Length > 0)
            {
                using var httpClient = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };
                var api = new ChargePilotApiClient(httpClient);
                var installationId = Guid.NewGuid();
                var enrollment = await api.EnrollAsync(
                    serverUri,
                    enrollmentCode,
                    installationId,
                    deviceName,
                    deviceClass);
                options = AgentOptions.Create(
                    serverUri.ToString(),
                    enrollment.Credential,
                    enrollment.EndpointId,
                    installationId,
                    deviceName,
                    deviceClass,
                    _agentVersion,
                    (int)_interval.Value);
            }
            else
            {
                if (_existingOptions is null)
                {
                    throw new InvalidOperationException("Enter an enrollment token to connect this device.");
                }

                if (_existingOptions.ServerUri != serverUri)
                {
                    throw new InvalidOperationException(
                        "The saved enrollment uses a different server. Enter a token to connect to this ChargePilot server.");
                }

                options = AgentOptions.Create(
                    serverUri.ToString(),
                    _existingOptions.Credential,
                    _existingOptions.EndpointId,
                    _existingOptions.InstallationId,
                    deviceName,
                    deviceClass,
                    _agentVersion,
                    (int)_interval.Value);
            }

            _configurationStore.Save(options);
            ServiceManager.InstallOrUpdate(Environment.ProcessPath
                ?? throw new InvalidOperationException("Unable to locate the ChargePilot Agent executable."));
            _existingOptions = options;
            _enrollmentToken.Clear();
            RefreshServiceStatus();
            ShowMessage("Device connected. The Windows service is running and will report on the selected interval.", isError: false);
        }
        catch (Exception exception)
        {
            ShowMessage(exception.Message, isError: true);
        }
        finally
        {
            SetBusy(false);
        }
    }

    private async Task UpdateAgentAsync()
    {
        if (_existingOptions is null || _serviceStatus.Text == "Not installed")
        {
            ShowMessage("Connect this device and install the service before updating.", isError: true);
            return;
        }

        SetBusy(true);
        ShowMessage("Checking the latest public agent release…", isError: false);
        try
        {
            using var httpClient = new HttpClient { Timeout = TimeSpan.FromMinutes(5) };
            httpClient.DefaultRequestHeaders.UserAgent.Add(
                new ProductInfoHeaderValue("ChargePilotAgentUpdater", _agentVersion));
            var releaseUri = new Uri(_existingOptions.ServerUri, "/api/v1/agent/releases/latest");
            using var releaseResponse = await httpClient.GetAsync(
                releaseUri,
                HttpCompletionOption.ResponseHeadersRead);
            releaseResponse.EnsureSuccessStatusCode();
            await using var releaseStream = await releaseResponse.Content.ReadAsStreamAsync();
            using var release = await JsonDocument.ParseAsync(releaseStream);

            var tag = release.RootElement.GetProperty("tag").GetString();
            if (tag is null || !tag.StartsWith("agents-v", StringComparison.Ordinal) ||
                !Version.TryParse(tag["agents-v".Length..], out var latestVersion))
            {
                throw new InvalidDataException("The ChargePilot API returned an invalid agent release version.");
            }

            if (latestVersion <= Version.Parse(_agentVersion))
            {
                ShowMessage($"This agent is up to date (version {_agentVersion}).", isError: false);
                return;
            }

            var asset = release.RootElement
                .GetProperty("assets")
                .EnumerateArray()
                .FirstOrDefault(item =>
                    item.TryGetProperty("name", out var name) &&
                    name.GetString() == "ChargePilotAgent.exe");
            if (asset.ValueKind == JsonValueKind.Undefined ||
                !asset.TryGetProperty("url", out var downloadUrlElement) ||
                !Uri.TryCreate(downloadUrlElement.GetString(), UriKind.Absolute, out var downloadUrl) ||
                !string.Equals(
                    downloadUrl.GetLeftPart(UriPartial.Authority),
                    _existingOptions.ServerUri.GetLeftPart(UriPartial.Authority),
                    StringComparison.OrdinalIgnoreCase) ||
                downloadUrl.AbsolutePath != "/agent/releases/latest/download/ChargePilotAgent.exe")
            {
                throw new InvalidDataException("The latest agent release does not contain the expected Windows download.");
            }

            var confirmation = MessageBox.Show(
                $"Update ChargePilot Agent from version {_agentVersion} to {latestVersion}?\n\nThe service will restart after the update.",
                "Update ChargePilot Agent",
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Question);
            if (confirmation != DialogResult.Yes)
            {
                ShowMessage("The update was cancelled.", isError: false);
                return;
            }

            ShowMessage($"Downloading version {latestVersion}…", isError: false);
            var updateDirectory = Path.Combine(
                Path.GetTempPath(),
                $"ChargePilotAgent-update-{Guid.NewGuid():N}");
            Directory.CreateDirectory(updateDirectory);
            var downloadedExecutable = Path.Combine(updateDirectory, "ChargePilotAgent.exe");
            await using (var downloadStream = await httpClient.GetStreamAsync(downloadUrl))
            await using (var fileStream = new FileStream(
                downloadedExecutable,
                FileMode.CreateNew,
                FileAccess.Write,
                FileShare.None,
                bufferSize: 81920,
                useAsync: true))
            {
                await downloadStream.CopyToAsync(fileStream);
            }

            ValidateDownloadedExecutable(downloadedExecutable, latestVersion);
            var updater = new ProcessStartInfo
            {
                FileName = downloadedExecutable,
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            updater.ArgumentList.Add("update");
            updater.ArgumentList.Add("--wait-for-process");
            updater.ArgumentList.Add(Environment.ProcessId.ToString());
            if (Process.Start(updater) is null)
            {
                throw new InvalidOperationException("Could not start the Windows agent updater.");
            }

            ShowMessage($"Updating to version {latestVersion}. This window will close while the service restarts.", isError: false);
            Close();
        }
        catch (Exception exception)
        {
            ShowMessage($"Could not update the agent: {exception.Message}", isError: true);
        }
        finally
        {
            if (!IsDisposed)
            {
                SetBusy(false);
            }
        }
    }

    private static void ValidateDownloadedExecutable(string path, Version expectedVersion)
    {
        using var stream = File.OpenRead(path);
        Span<byte> header = stackalloc byte[64];
        if (stream.Read(header) != header.Length ||
            header[0] != (byte)'M' ||
            header[1] != (byte)'Z')
        {
            throw new InvalidDataException("The downloaded agent is not a Windows executable.");
        }

        var peOffset = BitConverter.ToInt32(header[0x3C..0x40]);
        if (peOffset < header.Length || peOffset > stream.Length - 4)
        {
            throw new InvalidDataException("The downloaded agent has an invalid executable header.");
        }

        stream.Position = peOffset;
        Span<byte> signature = stackalloc byte[4];
        if (stream.Read(signature) != signature.Length ||
            !signature.SequenceEqual(new byte[] { (byte)'P', (byte)'E', 0, 0 }))
        {
            throw new InvalidDataException("The downloaded agent has an invalid executable signature.");
        }

        var fileVersion = FileVersionInfo.GetVersionInfo(path).ProductVersion;
        var reportedVersion = fileVersion?.Split('+', 2)[0];
        if (!Version.TryParse(reportedVersion, out var actualVersion) ||
            new Version(actualVersion.Major, actualVersion.Minor, Math.Max(0, actualVersion.Build)) != expectedVersion)
        {
            throw new InvalidDataException(
                $"The downloaded agent version did not match release {expectedVersion}.");
        }
    }

    private void RunServiceAction(Action action)
    {
        try
        {
            action();
            RefreshServiceStatus();
            ShowMessage($"Service is {_serviceStatus.Text.ToLowerInvariant()}.", isError: false);
        }
        catch (Exception exception)
        {
            ShowMessage(exception.Message, isError: true);
        }
    }

    private async Task DeregisterAsync()
    {
        if (_existingOptions is null)
        {
            return;
        }
        var result = MessageBox.Show(
            "Revoke this device's ChargePilot credential and stop its reports? You can enroll it again here with a new workspace token.",
            "Deregister ChargePilot Agent",
            MessageBoxButtons.YesNo,
            MessageBoxIcon.Warning);
        if (result != DialogResult.Yes)
        {
            return;
        }

        var options = _existingOptions;
        var serviceWasRunning = ServiceManager.GetStatus() == "Running";
        var credentialRevoked = false;
        SetBusy(true);
        try
        {
            if (serviceWasRunning)
            {
                ServiceManager.Stop();
            }
            using var httpClient = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };
            await new ChargePilotApiClient(httpClient).DeregisterAsync(options.ServerUri, options.Credential);
            credentialRevoked = true;
            _configurationStore.Delete();
            _existingOptions = null;
            _enrollmentToken.Clear();
            RefreshServiceStatus();
            ShowMessage("Device deregistered. Enter a new enrollment token to connect it again.", isError: false);
        }
        catch (Exception exception)
        {
            if (serviceWasRunning && !credentialRevoked)
            {
                try
                {
                    ServiceManager.Start();
                }
                catch (Exception restartException)
                {
                    ShowMessage(
                        $"{exception.Message} The service could not be restarted: {restartException.Message}",
                        isError: true);
                    return;
                }
            }
            ShowMessage(
                credentialRevoked
                    ? $"The server revoked this device, but local cleanup failed: {exception.Message}"
                    : exception.Message,
                isError: true);
        }
        finally
        {
            SetBusy(false);
        }
    }

    private void UninstallService()
    {
        var result = MessageBox.Show(
            "Remove the Windows service? The local enrollment will be kept so the service can be installed again.",
            "Uninstall ChargePilot Agent",
            MessageBoxButtons.YesNo,
            MessageBoxIcon.Question);
        if (result != DialogResult.Yes)
        {
            return;
        }

        RunServiceAction(() => ServiceManager.Uninstall(purgeConfiguration: false));
    }

    private void RefreshServiceStatus()
    {
        _serviceStatus.Text = ServiceManager.GetStatus();
        var isAdmin = ServiceManager.IsAdministrator();
        _uninstallButton.Enabled = isAdmin && _serviceStatus.Text != "Not installed";
        _updateButton.Enabled = isAdmin && _existingOptions is not null && _serviceStatus.Text != "Not installed";
    }

    private void SetBusy(bool busy)
    {
        _saveButton.Enabled = !busy && ServiceManager.IsAdministrator();
        _updateButton.Enabled = !busy &&
            ServiceManager.IsAdministrator() &&
            _existingOptions is not null &&
            _serviceStatus.Text != "Not installed";
        _startButton.Enabled = !busy && ServiceManager.IsAdministrator();
        _stopButton.Enabled = !busy && ServiceManager.IsAdministrator();
        _deregisterButton.Enabled = !busy && ServiceManager.IsAdministrator() && _existingOptions is not null;
        _uninstallButton.Enabled = !busy && ServiceManager.IsAdministrator() && _serviceStatus.Text != "Not installed";
        UseWaitCursor = busy;
    }

    private void ShowMessage(string message, bool isError)
    {
        _message.Text = message;
        _message.ForeColor = isError
            ? ColorTranslator.FromHtml("#934C37")
            : Leaf;
    }
}
