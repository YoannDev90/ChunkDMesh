using Eto.Drawing;
using Eto.Forms;
using ChunkDMesh.Client.Models;

namespace ChunkDMesh.Client.Controls;

public sealed class ProgressRing : Drawable
{
    private float _progress;
    private string _centerText = "";
    private ThemeColors _theme = ThemeColors.Dark;

    public ProgressRing()
    {
        Size = new Size(140, 140);
        MinimumSize = new Size(80, 80);
        _progress = 0;
    }

    public float Progress
    {
        get => _progress;
        set { _progress = Math.Clamp(value, 0, 1); Invalidate(); }
    }

    public string CenterText
    {
        get => _centerText;
        set { _centerText = value; Invalidate(); }
    }

    public void ApplyTheme(ThemeColors theme)
    {
        _theme = theme;
        Invalidate();
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        var g = e.Graphics;
        var rect = new RectangleF(PointF.Empty, Size);
        var cx = rect.X + rect.Width / 2f;
        var cy = rect.Y + rect.Height / 2f;
        var radius = Math.Min(rect.Width, rect.Height) / 2f - 14;
        var thickness = 8;

        // Drop shadow
        g.FillEllipse(new SolidBrush(Color.FromArgb(60, 0, 0, 0)), cx + 2, cy + 2, radius * 2, radius * 2);

        // Background track
        g.DrawEllipse(new Pen(_theme.Border, thickness), cx - radius, cy - radius, radius * 2, radius * 2);

        if (_progress > 0)
        {
            var sweepAngle = _progress * 360;
            var segments = Math.Max(16, (int)(sweepAngle / 3));

            // Glow pass
            using var glowPen = new Pen(_theme.Accent, thickness + 4)
            {
                LineCap = PenLineCap.Round,
            };
            for (int i = 0; i < segments; i++)
            {
                var a1 = -90 + (i * sweepAngle / segments) * Math.PI / 180;
                var a2 = -90 + ((i + 0.8f) * sweepAngle / segments) * Math.PI / 180;
                var x1 = cx + (radius - thickness / 2f) * (float)Math.Cos(a1);
                var y1 = cy + (radius - thickness / 2f) * (float)Math.Sin(a1);
                var x2 = cx + (radius - thickness / 2f) * (float)Math.Cos(a2);
                var y2 = cy + (radius - thickness / 2f) * (float)Math.Sin(a2);
                g.DrawLine(glowPen, x1, y1, x2, y2);
            }

            // Sharp pass
            using var sharpPen = new Pen(_theme.Accent, thickness)
            {
                LineCap = PenLineCap.Round,
            };
            for (int i = 0; i < segments; i++)
            {
                var a1 = -90 + (i * sweepAngle / segments) * Math.PI / 180;
                var a2 = -90 + ((i + 0.85f) * sweepAngle / segments) * Math.PI / 180;
                var x1 = cx + (radius - thickness / 2f) * (float)Math.Cos(a1);
                var y1 = cy + (radius - thickness / 2f) * (float)Math.Sin(a1);
                var x2 = cx + (radius - thickness / 2f) * (float)Math.Cos(a2);
                var y2 = cy + (radius - thickness / 2f) * (float)Math.Sin(a2);
                g.DrawLine(sharpPen, x1, y1, x2, y2);
            }
        }

        // Center text
        var pct = $"{(_progress * 100):F0}%";
        var font = Fonts.Sans(24, FontStyle.Bold);
        var fh = font.MeasureString(pct).Height;
        g.DrawText(font, _theme.TextPrimary, cx - font.MeasureString(pct).Width / 2, cy - fh / 2 - 8, pct);

        if (!string.IsNullOrEmpty(_centerText))
        {
            var subFont = Fonts.Sans(10);
            g.DrawText(subFont, _theme.TextSecondary,
                cx - subFont.MeasureString(_centerText).Width / 2, cy + fh / 2 - 4, _centerText);
        }
    }
}