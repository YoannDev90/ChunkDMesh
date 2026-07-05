using ChunkDMesh.Client;
using Eto.Forms;

namespace ChunkDMesh.Client;

public static class Program
{
    [STAThread]
    public static void Main(string[] args)
    {
        var app = new Application(Eto.Platform.Detect);
        app.Name = "ChunkDMesh";
        app.Run(new MainForm());
    }
}
