// Installation metadata never grants permission to destroy persistent data.
function needsSetup(record) {
  return record === null;
}
function validateProfile(profile) {
  if (
    !profile ||
    profile.schema !== 1 ||
    !/^[a-f0-9-]{36}$/.test(profile.id) ||
    !/^[a-f0-9-]{36}$/.test(profile.connectionId) ||
    ![
      profile.username,
      profile.dbPassword,
      profile.wahaKey,
      profile.webhookSecret,
    ].every((value) => typeof value === "string" && value.length > 0)
  )
    throw new Error("PRIVATE_PROFILE_UNREADABLE");
  return profile;
}
function price(value) {
  return (
    typeof value === "string" &&
    /^\d+(\.\d+)?$/.test(value) &&
    Number.isFinite(Number(value)) &&
    Number(value) >= 0
  );
}
function aiReady(profile) {
  return (
    profile.aiEnabled === true &&
    !!profile.modelKey &&
    price(profile.inputPrice) &&
    price(profile.outputPrice) &&
    price(profile.budget) &&
    Number(profile.budget) > 0 &&
    Number(profile.budget) <= 10
  );
}
function updateAI(profile, options) {
  if (
    options.modelKey !== undefined &&
    (typeof options.modelKey !== "string" ||
      options.modelKey.length > 512 ||
      /[\r\n\0]/.test(options.modelKey))
  )
    throw new Error("INVALID_SETTINGS");
  if (options.modelKey) profile.modelKey = options.modelKey.trim();
  if (options.clearKey === true) profile.modelKey = "";
  for (const field of ["inputPrice", "outputPrice", "budget"]) {
    if (options[field] !== undefined) {
      if (typeof options[field] !== "string" || options[field].length > 40)
        throw new Error("INVALID_SETTINGS");
      profile[field] = options[field].trim();
    }
  }
  if (options.aiEnabled !== undefined) {
    if (
      typeof options.aiEnabled !== "boolean" ||
      (options.aiEnabled && options.aiConsent !== true)
    )
      throw new Error("INVALID_SETTINGS");
    profile.aiEnabled = options.aiEnabled;
  }
  return profile;
}
module.exports = { needsSetup, validateProfile, aiReady, updateAI };
