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
    private readonly TextBox _serverUrl = new() { Dock = DockStyle.Fill };
    private readonly TextBox _deviceName = new() { Dock = DockStyle.Fill };
    private readonly ComboBox _deviceClass = new() { Dock = DockStyle.Left, DropDownStyle = ComboBoxStyle.DropDownList, Width = 180 };
    private readonly NumericUpDown _interval = new() { Minimum = 1, Maximum = 60, Value = 5, Width = 180 };
    private readonly TextBox _enrollmentToken = new() { Dock = DockStyle.Fill, UseSystemPasswordChar = true };
    private readonly Label _serviceStatus = new() { AutoSize = true, Font = new Font("Segoe UI", 11, FontStyle.Bold), ForeColor = Forest };
    private readonly Label _message = new() { AutoSize = true, MaximumSize = new Size(660, 0) };
    private readonly Button _saveButton = new() { Text = "Save and start service", AutoSize = true, BackColor = Leaf, ForeColor = Color.White, FlatStyle = FlatStyle.Flat };
    private readonly Button _startButton = new() { Text = "Start", AutoSize = true };
    private readonly Button _stopButton = new() { Text = "Stop", AutoSize = true };
    private readonly Button _uninstallButton = new() { Text = "Uninstall service", AutoSize = true };
    private readonly string _agentVersion;
    private AgentOptions? _existingOptions;

    public SetupForm(string serverUrl, string agentVersion)
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
        page.Controls.Add(statusLine, 0, 2);

        var fields = new TableLayoutPanel
        {
            AutoSize = true,
            Dock = DockStyle.Top,
            ColumnCount = 2,
            RowCount = 5,
            Margin = new Padding(0, 0, 0, 16),
        };
        fields.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 174));
        fields.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        for (var index = 0; index < 5; index++)
        {
            fields.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        }
        AddField(fields, 0, "ChargePilot server", _serverUrl);
        AddField(fields, 1, "Device name", _deviceName);
        AddField(fields, 2, "Device class", _deviceClass);
        AddField(fields, 3, "Report every (minutes)", _interval);
        AddField(fields, 4, "Enrollment token", _enrollmentToken);

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
            Text = "Leave the token blank to keep the current enrollment. New tokens are entered here and never saved in the command line.",
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
        _startButton.Click += (_, _) => RunServiceAction(ServiceManager.Start);
        _stopButton.Click += (_, _) => RunServiceAction(ServiceManager.Stop);
        _uninstallButton.Click += (_, _) => UninstallService();
        actions.Controls.AddRange([_saveButton, _startButton, _stopButton, _uninstallButton]);
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
        _startButton.Enabled = isAdmin;
        _stopButton.Enabled = isAdmin;
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

    private void LoadConfiguration(string serverUrl)
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

        _serverUrl.Text = _existingOptions?.ServerUri.ToString() ?? serverUrl;
        _deviceName.Text = _existingOptions?.DeviceName ?? Environment.MachineName;
        _deviceClass.SelectedItem = _existingOptions?.DeviceClass == "desktop" ? "Desktop" : "Laptop";
        _interval.Value = _existingOptions?.IntervalMinutes ?? 5;
    }

    private async Task SaveAndStartAsync()
    {
        SetBusy(true);
        try
        {
            if (!Uri.TryCreate(_serverUrl.Text.Trim().TrimEnd('/'), UriKind.Absolute, out var serverUri))
            {
                throw new ArgumentException("Enter a valid ChargePilot server URL.");
            }

            var deviceClass = _deviceClass.SelectedItem?.ToString()?.ToLowerInvariant()
                ?? throw new ArgumentException("Select a device class.");
            var deviceName = _deviceName.Text.Trim();
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
                    throw new InvalidOperationException("Enter a new enrollment token when changing the server URL.");
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
        _uninstallButton.Enabled = ServiceManager.IsAdministrator() && _serviceStatus.Text != "Not installed";
    }

    private void SetBusy(bool busy)
    {
        _saveButton.Enabled = !busy && ServiceManager.IsAdministrator();
        _startButton.Enabled = !busy && ServiceManager.IsAdministrator();
        _stopButton.Enabled = !busy && ServiceManager.IsAdministrator();
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
