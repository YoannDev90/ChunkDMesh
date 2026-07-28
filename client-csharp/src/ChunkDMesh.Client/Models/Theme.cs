using Eto.Drawing;

namespace ChunkDMesh.Client.Models;

public sealed record ThemeColors
{
    public Color BgDark { get; init; }
    public Color BgCard { get; init; }
    public Color BgInput { get; init; }
    public Color TextPrimary { get; init; }
    public Color TextSecondary { get; init; }
    public Color TextMuted { get; init; }
    public Color Accent { get; init; }
    public Color AccentHover { get; init; }
    public Color Success { get; init; }
    public Color Warning { get; init; }
    public Color Danger { get; init; }
    public Color Border { get; init; }
    public Color ChartLine { get; init; }
    public Color ChartFill { get; init; }

    public static ThemeColors Dark => new()
    {
        BgDark = Color.FromArgb(18, 18, 24),
        BgCard = Color.FromArgb(28, 28, 36),
        BgInput = Color.FromArgb(38, 38, 48),
        TextPrimary = Color.FromArgb(230, 230, 240),
        TextSecondary = Color.FromArgb(160, 160, 175),
        TextMuted = Color.FromArgb(100, 100, 115),
        Accent = Color.FromArgb(99, 102, 241),
        AccentHover = Color.FromArgb(129, 132, 255),
        Success = Color.FromArgb(52, 211, 153),
        Warning = Color.FromArgb(251, 191, 36),
        Danger = Color.FromArgb(239, 68, 68),
        Border = Color.FromArgb(48, 48, 58),
        ChartLine = Color.FromArgb(99, 102, 241),
        ChartFill = Color.FromArgb(30, 32, 80, 128),
    };

    public static ThemeColors Light => new()
    {
        BgDark = Color.FromArgb(245, 245, 250),
        BgCard = Color.FromArgb(255, 255, 255),
        BgInput = Color.FromArgb(240, 240, 245),
        TextPrimary = Color.FromArgb(20, 20, 30),
        TextSecondary = Color.FromArgb(80, 80, 95),
        TextMuted = Color.FromArgb(140, 140, 155),
        Accent = Color.FromArgb(99, 102, 241),
        AccentHover = Color.FromArgb(79, 82, 221),
        Success = Color.FromArgb(16, 185, 129),
        Warning = Color.FromArgb(217, 119, 6),
        Danger = Color.FromArgb(220, 38, 38),
        Border = Color.FromArgb(220, 220, 230),
        ChartLine = Color.FromArgb(99, 102, 241),
        ChartFill = Color.FromArgb(99, 102, 241, 40),
    };
}
