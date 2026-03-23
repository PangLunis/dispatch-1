/**
 * Custom Expo config plugin to inject iOS code signing settings.
 *
 * expo-build-properties doesn't support DEVELOPMENT_TEAM or CODE_SIGN_STYLE,
 * so we use withXcodeProject to set them directly in the pbxproj.
 *
 * Config comes from app.yaml (gitignored, instance-specific):
 *   developmentTeam: "YOUR_TEAM_ID"
 *   codeSignStyle: "Automatic"  # or "Manual"
 *   provisioningProfile: "Profile Name"  # only for Manual
 */
const { withXcodeProject } = require("expo/config-plugins");

function withSigningConfig(config, props) {
  return withXcodeProject(config, (mod) => {
    const project = mod.modResults;
    const configurations = project.pbxXCBuildConfigurationSection();

    for (const key in configurations) {
      if (typeof configurations[key] !== "object") continue;

      const buildSettings = configurations[key].buildSettings;
      if (!buildSettings) continue;

      // Only modify app target configs (not Pods or other targets)
      if (!buildSettings.INFOPLIST_FILE) continue;

      if (props.developmentTeam) {
        buildSettings.DEVELOPMENT_TEAM = `"${props.developmentTeam}"`;
      }
      if (props.codeSignStyle) {
        buildSettings.CODE_SIGN_STYLE = `"${props.codeSignStyle}"`;
      }
      if (props.provisioningProfile) {
        buildSettings.PROVISIONING_PROFILE_SPECIFIER = `"${props.provisioningProfile}"`;
      }
    }

    return mod;
  });
}

module.exports = withSigningConfig;
