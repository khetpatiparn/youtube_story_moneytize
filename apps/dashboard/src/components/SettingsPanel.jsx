import React from "react";

const secretFields = [
  ["gemini_api_key", "Gemini API key", "gemini"],
  ["cloudflare_account_id", "Cloudflare account id", "cloudflare"],
  ["cloudflare_api_token", "Cloudflare API token", "cloudflare"],
];

function secretSummary(value) {
  return value?.configured ? `Configured (...${value.suffix ?? ""})` : "Not configured";
}

export function SettingsPanel({
  busy,
  error,
  onChange,
  onSave,
  onTest,
  value,
}) {
  return (
    <section className="panel">
      <h2>SettingsPanel</h2>
      <form className="form-stack" onSubmit={onSave}>
        <label>
          Story provider
          <select name="story_provider" onChange={onChange} value={value.story_provider}>
            <option value="local">local</option>
            <option value="gemini">gemini</option>
          </select>
        </label>
        <label>
          Image provider
          <select name="image_provider" onChange={onChange} value={value.image_provider}>
            <option value="local">local</option>
            <option value="cloudflare">cloudflare</option>
          </select>
        </label>
        <label>
          Projects directory
          <input name="projects_dir" onChange={onChange} value={value.projects_dir} />
        </label>
        <label>
          Image retry limit
          <input name="image_retry_limit" onChange={onChange} type="number" value={value.image_retry_limit} />
        </label>
        {secretFields.map(([name, label, provider]) => (
          <div className="secret-row" key={name}>
            <label>
              {label}
              <input name={name} onChange={onChange} type="password" value={value[name]} />
            </label>
            <small>{secretSummary(value[`${name}_status`])}</small>
            <button className="action-button" disabled={busy} onClick={() => onTest(provider)} type="button">
              Test
            </button>
          </div>
        ))}
        <button className="action-button primary" disabled={busy} type="submit">
          Save settings
        </button>
        {error ? <p className="action-message error">{error}</p> : null}
      </form>
    </section>
  );
}
