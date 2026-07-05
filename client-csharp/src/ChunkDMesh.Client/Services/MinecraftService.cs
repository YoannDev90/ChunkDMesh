using System.Diagnostics;
using System.IO.Compression;
using System.Net.Http.Json;
using System.Text.Json;

namespace ChunkDMesh.Client.Services;

/// <summary>Manages Minecraft server lifecycle: Java detection, download, mods, launch.</summary>
public sealed class MinecraftService
{
    private readonly string _workDir;
    private Process? _serverProcess;

    public MinecraftService(string workDir) => _workDir = workDir;

    public string JavaPath { get; private set; } = "java";
    public string ServerDir => Path.Combine(_workDir, "server");
    public bool IsRunning => _serverProcess?.HasExited == false;

    // ── Java detection ──────────────────────────────────

    public string? DetectJava()
    {
        var candidates = new[]
        {
            "java",
            "/usr/lib/jvm/java-21-openjdk/bin/java",
            "/usr/lib/jvm/java-17-openjdk/bin/java",
            "/usr/lib/jvm/java-8-openjdk/bin/java",
        };

        if (OperatingSystem.IsWindows())
        {
            var pf = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
            candidates = [
                Path.Combine(pf, "Java", "bin", "java.exe"),
                Path.Combine(pf, "Eclipse Adoptium", "jdk-21.0.2.13-hotspot", "bin", "java.exe"),
            ];
        }

        foreach (var path in candidates)
        {
            try
            {
                var psi = new ProcessStartInfo(path, "-version")
                {
                    RedirectStandardError = true,
                    UseShellExecute = false
                };
                var proc = Process.Start(psi);
                proc!.WaitForExit(5000);
                if (proc.ExitCode == 0)
                    return JavaPath = path;
            }
            catch { }
        }

        return null;
    }

    public async Task DownloadJavaAsync(IProgress<double>? progress = null, CancellationToken ct = default)
    {
        // Adoptium API — get latest JDK 21 for current platform
        var os = GetOs();
        var arch = GetArch();
        var url = $"https://api.adoptium.net/v3/binary/version/jdk-21.0.2%2B13/linux/{arch}/jdk/hotspot/normal/eclipse";

        if (OperatingSystem.IsWindows())
            url = $"https://api.adoptium.net/v3/binary/version/jdk-21.0.2%2B13/windows/{arch}/jdk/hotspot/normal/eclipse";

        using var http = new HttpClient { Timeout = TimeSpan.FromMinutes(10) };
        var resp = await http.GetAsync(url, HttpCompletionOption.ResponseHeadersRead, ct);
        resp.EnsureSuccessStatusCode();

        var total = resp.Content.Headers.ContentLength ?? -1;
        var jdkDir = Path.Combine(_workDir, "jdk");
        Directory.CreateDirectory(jdkDir);

        await using var stream = await resp.Content.ReadAsStreamAsync(ct);
        var archive = Path.Combine(jdkDir, "jdk.tar.gz");
        await using var fs = File.Create(archive);

        var buffer = new byte[81920];
        long read = 0;
        int bytes;
        while ((bytes = await stream.ReadAsync(buffer, ct)) > 0)
        {
            await fs.WriteAsync(buffer.AsMemory(0, bytes), ct);
            read += bytes;
            progress?.Report((double)read / total);
        }

        await fs.DisposeAsync();

        // Extract
        if (OperatingSystem.IsLinux() || OperatingSystem.IsMacOS())
        {
            await Process.Start("tar", $"-xzf {archive} -C {jdkDir}").WaitForExitAsync(ct);
            JavaPath = Directory.GetFiles(jdkDir, "java", SearchOption.AllDirectories).FirstOrDefault() ?? "java";
        }
        else
        {
            ZipFile.ExtractToDirectory(archive, jdkDir);
            JavaPath = Directory.GetFiles(jdkDir, "java.exe", SearchOption.AllDirectories).FirstOrDefault() ?? "java";
        }

        File.Delete(archive);
    }

    // ── Mods download ───────────────────────────────────

    public async Task DownloadModsAsync(byte[] modsZip, CancellationToken ct = default)
    {
        var modsDir = Path.Combine(ServerDir, "mods");
        Directory.CreateDirectory(modsDir);

        var zipPath = Path.Combine(ServerDir, "mods.zip");
        await File.WriteAllBytesAsync(zipPath, modsZip, ct);
        ZipFile.ExtractToDirectory(zipPath, modsDir, overwriteFiles: true);
        File.Delete(zipPath);
    }

    // ── Server.properties ───────────────────────────────

    public async Task WriteServerPropertiesAsync(int rconPort, string rconPassword, CancellationToken ct = default)
    {
        var props = new Dictionary<string, string>
        {
            ["server-port"] = "25565",
            ["enable-rcon"] = "true",
            ["rcon.port"] = rconPort.ToString(),
            ["rcon.password"] = rconPassword,
            ["broadcast-rcon-to-ops"] = "false",
            ["level-seed"] = "",
            ["gamemode"] = "spectator",
            ["spawn-monsters"] = "false",
            ["spawn-animals"] = "false",
            ["spawn-npcs"] = "false",
            ["online-mode"] = "false",
            ["max-players"] = "0",
            ["pvp"] = "false",
            ["difficulty"] = "peaceful",
            ["allow-nether"] = "false",
            ["enable-query"] = "false",
            ["sync-chunk-writes"] = "true",
        };

        var lines = props.Select(kv => $"{kv.Key}={kv.Value}");
        await File.WriteAllLinesAsync(Path.Combine(ServerDir, "server.properties"), lines, ct);
    }

    // ── Launch ──────────────────────────────────────────

    public async Task LaunchServerAsync(CancellationToken ct = default)
    {
        var jar = Directory.GetFiles(ServerDir, "*.jar").FirstOrDefault(f => f.Contains("server"));
        if (jar == null)
            throw new FileNotFoundException("No server jar found in " + ServerDir);

        var psi = new ProcessStartInfo(JavaPath)
        {
            Arguments = $"-Xmx2G -Xms512M -jar \"{jar}\" nogui",
            WorkingDirectory = ServerDir,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };

        _serverProcess = Process.Start(psi);
        if (_serverProcess == null)
            throw new InvalidOperationException("Failed to start Minecraft server");

        // Read output until "Done" appears
        using var reader = _serverProcess.StandardOutput;
        string? line;
        while ((line = await reader.ReadLineAsync(ct)) != null)
        {
            if (line.Contains("Done", StringComparison.OrdinalIgnoreCase))
                return;
            if (line.Contains("Failed to start", StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Minecraft server failed to start: " + line);
        }
    }

    public async Task StopServerAsync()
    {
        if (_serverProcess?.HasExited == false)
        {
            using var rcon = new RconService("127.0.0.1", 25575, "");
            await rcon.ConnectAsync();
            await rcon.RunAsync("stop");
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(30));
            try { await _serverProcess.WaitForExitAsync(cts.Token); } catch { _serverProcess.Kill(); }
        }
    }

    // ── Helpers ─────────────────────────────────────────

    private static string GetOs() =>
        OperatingSystem.IsWindows() ? "windows" :
        OperatingSystem.IsMacOS() ? "mac" : "linux";

    private static string GetArch() =>
        Environment.Is64BitOperatingSystem ? "x64" : "x86";
}
