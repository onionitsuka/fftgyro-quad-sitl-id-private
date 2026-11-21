using UnityEditor;
using UnityEditor.SceneManagement;
public static class LocalOfficialLinux {
    public static void Build() {
        PlayerSettings.runInBackground = true;
        var report = BuildPipeline.BuildPlayer(new BuildPlayerOptions {
            scenes = new [] { "Assets/Scenes/Avatar.unity" },
            locationPathName = "../../Build/Hakoniwa.x86_64",
            target = BuildTarget.StandaloneLinux64,
            options = BuildOptions.None
        });
        if (report.summary.result != UnityEditor.Build.Reporting.BuildResult.Succeeded)
            throw new System.Exception("Official Avatar build failed");
    }
    public static void Open() {
        EditorSceneManager.OpenScene("Assets/Scenes/Avatar.unity");
    }
}
