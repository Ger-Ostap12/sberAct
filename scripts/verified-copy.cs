using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;

public static class SberActVerifiedCopy
{
    private sealed class CopyFile
    {
        public string Source;
        public string Target;
        public long Size;
        public DateTime Modified;
    }
    private static void CheckPath(string path)
    {
        string cursor = Path.GetFullPath(path);
        while (!String.IsNullOrEmpty(cursor))
        {
            if ((Directory.Exists(cursor) || File.Exists(cursor)) &&
                (File.GetAttributes(cursor) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("Reparse point is not supported: " + cursor);
            string parent = Path.GetDirectoryName(cursor);
            if (parent == cursor) break;
            cursor = parent;
        }
    }
    public static void Copy(string source, string target, Action<long, long, int, int, string> progress)
    {
        source = Path.GetFullPath(source).TrimEnd(Path.DirectorySeparatorChar);
        target = Path.GetFullPath(target).TrimEnd(Path.DirectorySeparatorChar);
        if (source.Equals(target, StringComparison.OrdinalIgnoreCase) ||
            source.StartsWith(target + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) ||
            target.StartsWith(source + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new IOException("Copy directories overlap");
        CheckPath(source);
        CheckPath(target);
        var directories = new Stack<KeyValuePair<string, string>>();
        var files = new List<CopyFile>();
        long totalBytes = 0;
        var timer = Stopwatch.StartNew();
        directories.Push(new KeyValuePair<string, string>(source, target));
        if (progress != null) progress(0, 0, 0, 0, "Scanning files");
        while (directories.Count > 0)
        {
            var pair = directories.Pop();
            if (Directory.Exists(pair.Value) &&
                (File.GetAttributes(pair.Value) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("Destination directory is a reparse point: " + pair.Value);
            Directory.CreateDirectory(pair.Value);
            foreach (string entry in Directory.EnumerateFileSystemEntries(pair.Key))
            {
                FileAttributes attributes = File.GetAttributes(entry);
                if ((attributes & FileAttributes.ReparsePoint) != 0)
                    throw new IOException("Source contains a reparse point: " + entry);
                string destination = Path.Combine(pair.Value, Path.GetFileName(entry));
                if ((attributes & FileAttributes.Directory) != 0)
                    directories.Push(new KeyValuePair<string, string>(entry, destination));
                else
                {
                    if (File.Exists(destination) && (File.GetAttributes(destination) & FileAttributes.ReparsePoint) != 0)
                        throw new IOException("Destination file is a reparse point: " + destination);
                    var info = new FileInfo(entry);
                    files.Add(new CopyFile { Source = entry, Target = destination, Size = info.Length, Modified = info.LastWriteTimeUtc });
                    totalBytes += info.Length;
                }
            }
            if (progress != null && timer.ElapsedMilliseconds >= 1000)
            {
                progress(0, totalBytes, 0, files.Count, "Scanning files");
                timer.Restart();
            }
        }
        long copied = 0;
        int done = 0;
        byte[] buffer = new byte[1024 * 1024];
        if (progress != null) progress(0, totalBytes, 0, files.Count, "Copying and verifying");
        foreach (var file in files)
        {
            string temporary = Path.Combine(Path.GetDirectoryName(file.Target), ".sbc-" + Guid.NewGuid().ToString("N").Substring(0, 16));
            bool temporaryCreated = false;
            try
            {
                byte[] expected;
                using (var hash = SHA256.Create())
                using (var input = new FileStream(file.Source, FileMode.Open, FileAccess.Read, FileShare.Read, 4096, FileOptions.SequentialScan))
                using (var output = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None, 4096, FileOptions.SequentialScan))
                {
                    temporaryCreated = true;
                    if (input.Length != file.Size) throw new IOException("Source size changed: " + file.Source);
                    int count;
                    while ((count = input.Read(buffer, 0, buffer.Length)) > 0)
                    {
                        hash.TransformBlock(buffer, 0, count, buffer, 0);
                        output.Write(buffer, 0, count);
                        copied += count;
                        if (progress != null && timer.ElapsedMilliseconds >= 1000)
                        {
                            progress(copied, totalBytes, done, files.Count, "Copying and verifying");
                            timer.Restart();
                        }
                    }
                    hash.TransformFinalBlock(new byte[0], 0, 0);
                    expected = hash.Hash;
                }
                byte[] actual;
                using (var hash = SHA256.Create())
                using (var input = new FileStream(temporary, FileMode.Open, FileAccess.Read, FileShare.Read, 4096, FileOptions.SequentialScan))
                {
                    int count;
                    while ((count = input.Read(buffer, 0, buffer.Length)) > 0)
                    {
                        hash.TransformBlock(buffer, 0, count, buffer, 0);
                        if (progress != null && timer.ElapsedMilliseconds >= 1000)
                        {
                            progress(copied, totalBytes, done, files.Count, "Verifying copied data");
                            timer.Restart();
                        }
                    }
                    hash.TransformFinalBlock(new byte[0], 0, 0);
                    actual = hash.Hash;
                }
                for (int i = 0; i < actual.Length; i++)
                    if (actual[i] != expected[i]) throw new IOException("Copy checksum mismatch: " + file.Source);
                if (File.Exists(file.Target))
                {
                    FileAttributes attributes = File.GetAttributes(file.Target);
                    bool readOnly = (attributes & FileAttributes.ReadOnly) != 0;
                    if (readOnly) File.SetAttributes(file.Target, attributes & ~FileAttributes.ReadOnly);
                    try { File.Replace(temporary, file.Target, null); }
                    catch
                    {
                        if (readOnly && File.Exists(file.Target)) File.SetAttributes(file.Target, attributes);
                        throw;
                    }
                }
                else
                    File.Move(temporary, file.Target);
                File.SetLastWriteTimeUtc(file.Target, file.Modified);
                done++;
                if (progress != null && (done == files.Count || timer.ElapsedMilliseconds >= 1000))
                {
                    progress(copied, totalBytes, done, files.Count, "Copying and verifying");
                    timer.Restart();
                }
            }
            finally
            {
                if (temporaryCreated && File.Exists(temporary)) File.Delete(temporary);
            }
        }
    }
}
