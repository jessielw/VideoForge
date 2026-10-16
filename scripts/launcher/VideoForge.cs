// VideoForge.exe, the portable build's launcher: runs its own Python on `videoforge serve --window`
// (or on the arguments given), with VIDEOFORGE_ROOT set to its folder so videoforge.toml, tools/ and
// the frontend are found there. Built by scripts/build_portable.py with the csc.exe Windows ships.
using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Windows.Forms;

static class Launcher
{
    [STAThread]
    static int Main(string[] args)
    {
        string root = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\');
        string python = Path.Combine(root, "runtime", "pythonw.exe");
        if (!File.Exists(python))
        {
            MessageBox.Show("Python wasn't found at " + python + ".\nUnpack the whole folder again.", "VideoForge",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        string[] command = args.Length > 0 ? args : new[] { "serve", "--window" };
        var info = new ProcessStartInfo(python)
        {
            Arguments = "-m videoforge " + string.Join(" ", command.Select(Quote)),
            WorkingDirectory = root,
            UseShellExecute = false,
        };
        info.EnvironmentVariables["VIDEOFORGE_ROOT"] = root;
        try
        {
            Process.Start(info);
            return 0;
        }
        catch (Exception e)
        {
            MessageBox.Show("VideoForge didn't start: " + e.Message, "VideoForge", MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return 1;
        }
    }

    static string Quote(string arg)
    {
        return arg.Length > 0 && arg.IndexOfAny(new[] { ' ', '\t', '"' }) < 0 ? arg : "\"" + arg.Replace("\"", "\\\"") + "\"";
    }
}
