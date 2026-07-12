"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { Keyboard, Monitor, Moon, Sun } from "lucide-react";

import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Field } from "@/components/ui/Field";
import { Alert } from "@/components/ui/Feedback";
import { getApiErrorMessage } from "@/lib/api/client";
import { systemApi } from "@/lib/api/system";
import { cn } from "@/lib/utils";
import {
  changePasswordSchema,
  profileSchema,
  type ChangePasswordInput,
  type ProfileInput,
} from "@/lib/validations";
import type { MeetingSource } from "@/lib/types";
import { useAuthStore } from "@/store/auth";
import { useTourStore } from "@/store/tour";
import { useThemeStore, type ThemeMode } from "@/store/theme";
import { usePreferencesStore } from "@/store/preferences";
import { useChangePassword, useUpdateProfile } from "@/hooks/useAuth";
import { useResetDemo } from "@/hooks/useDemo";

const SOURCE_OPTIONS: { value: MeetingSource; label: string }[] = [
  { value: "manual_upload", label: "Manual upload" },
  { value: "zoom", label: "Zoom" },
  { value: "google_meet", label: "Google Meet" },
  { value: "ms_teams", label: "Microsoft Teams" },
  { value: "mobile_recording", label: "Mobile recording" },
  { value: "voice_recorder", label: "Voice recorder" },
  { value: "other", label: "Other" },
];

const THEME_OPTIONS: { value: ThemeMode; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
];

function AppearanceSection() {
  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Appearance</CardTitle>
      </CardHeader>
      <CardBody className="space-y-3">
        <p className="text-sm text-muted">Choose how MeetingMind looks. System follows your device.</p>
        <div className="grid max-w-md grid-cols-3 gap-2">
          {THEME_OPTIONS.map(({ value, label, icon: Icon }) => (
            <button
              key={value}
              onClick={() => setTheme(value)}
              aria-pressed={theme === value}
              className={cn(
                "flex flex-col items-center gap-2 rounded-xl border p-4 transition-colors",
                theme === value
                  ? "border-brand-400 bg-brand-50 text-brand-700"
                  : "border-border bg-surface text-muted hover:text-foreground",
              )}
            >
              <Icon className="h-5 w-5" />
              <span className="text-sm font-medium">{label}</span>
            </button>
          ))}
        </div>
      </CardBody>
    </Card>
  );
}

function PreferencesSection() {
  const notifyOnComplete = usePreferencesStore((s) => s.notifyOnComplete);
  const setNotifyOnComplete = usePreferencesStore((s) => s.setNotifyOnComplete);
  const defaultSource = usePreferencesStore((s) => s.defaultSource);
  const setDefaultSource = usePreferencesStore((s) => s.setDefaultSource);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Preferences</CardTitle>
      </CardHeader>
      <CardBody className="space-y-5">
        <label className="flex items-center justify-between gap-4">
          <span>
            <span className="block text-sm font-medium text-foreground">Processing notifications</span>
            <span className="block text-xs text-muted">Show a toast when a meeting finishes transcribing.</span>
          </span>
          <input
            type="checkbox"
            checked={notifyOnComplete}
            onChange={(e) => setNotifyOnComplete(e.target.checked)}
            className="h-5 w-5 accent-brand-600"
          />
        </label>

        <Field label="Default upload source" htmlFor="default-source" hint="Pre-selected on the upload page.">
          <select
            id="default-source"
            value={defaultSource}
            onChange={(e) => setDefaultSource(e.target.value as MeetingSource)}
            className="h-10 w-full max-w-xs rounded-lg border border-border bg-surface px-3 text-sm text-foreground focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-200"
          >
            {SOURCE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </Field>

        <div className="flex items-center gap-2 text-sm text-muted">
          <Keyboard className="h-4 w-4" />
          Press <kbd className="rounded border border-border bg-slate-50 px-1.5 py-0.5 font-mono text-xs">?</kbd> anywhere
          to see keyboard shortcuts.
        </div>
      </CardBody>
    </Card>
  );
}

function SystemSection() {
  const { data, isLoading } = useQuery({ queryKey: ["system-info"], queryFn: () => systemApi.info() });
  const rows: { label: string; value: string }[] = data
    ? [
        { label: "AI model", value: `${data.ai_provider} · ${data.ai_model}` },
        { label: "Embeddings", value: data.embedding_provider },
        { label: "Transcription", value: `${data.stt_provider} · ${data.whisper_model} (${data.whisper_device})` },
        { label: "Processing", value: data.async_processing ? "Async worker" : "Inline (eager)" },
        { label: "Storage", value: data.storage_backend },
        { label: "Max upload", value: data.max_upload_mb ? `${data.max_upload_mb} MB` : "—" },
      ]
    : [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>System</CardTitle>
      </CardHeader>
      <CardBody>
        <p className="mb-3 text-sm text-muted">The local providers and models MeetingMind is running (read-only).</p>
        {isLoading ? (
          <p className="text-sm text-muted">Loading…</p>
        ) : (
          <dl className="grid gap-x-8 gap-y-2 sm:grid-cols-2">
            {rows.map((r) => (
              <div key={r.label} className="flex items-center justify-between border-b border-border py-1.5">
                <dt className="text-sm text-muted">{r.label}</dt>
                <dd className="text-sm font-medium text-foreground">{r.value}</dd>
              </div>
            ))}
          </dl>
        )}
      </CardBody>
    </Card>
  );
}

function ProfileSection() {
  const user = useAuthStore((s) => s.user);
  const updateProfile = useUpdateProfile();
  const {
    register,
    handleSubmit,
    formState: { errors, isDirty },
  } = useForm<ProfileInput>({
    resolver: zodResolver(profileSchema),
    defaultValues: { first_name: user?.first_name ?? "", last_name: user?.last_name ?? "" },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Profile</CardTitle>
      </CardHeader>
      <CardBody>
        <form onSubmit={handleSubmit((v) => updateProfile.mutate(v))} className="space-y-4">
          {updateProfile.isSuccess && <Alert variant="success">Profile updated.</Alert>}
          {updateProfile.isError && <Alert>{getApiErrorMessage(updateProfile.error)}</Alert>}

          <Field label="Email">
            <Input value={user?.email ?? ""} disabled />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="First name" htmlFor="first_name" error={errors.first_name?.message}>
              <Input id="first_name" {...register("first_name")} />
            </Field>
            <Field label="Last name" htmlFor="last_name" error={errors.last_name?.message}>
              <Input id="last_name" {...register("last_name")} />
            </Field>
          </div>
          <div className="flex justify-end">
            <Button type="submit" isLoading={updateProfile.isPending} disabled={!isDirty}>
              Save changes
            </Button>
          </div>
        </form>
      </CardBody>
    </Card>
  );
}

function PasswordSection() {
  const changePassword = useChangePassword();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ChangePasswordInput>({ resolver: zodResolver(changePasswordSchema) });

  const onSubmit = (values: ChangePasswordInput) =>
    changePassword.mutate(
      { current_password: values.current_password, new_password: values.new_password },
      { onSuccess: () => reset() },
    );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Change password</CardTitle>
      </CardHeader>
      <CardBody>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {changePassword.isSuccess && <Alert variant="success">Password changed.</Alert>}
          {changePassword.isError && <Alert>{getApiErrorMessage(changePassword.error)}</Alert>}

          <Field label="Current password" htmlFor="current_password" error={errors.current_password?.message}>
            <Input id="current_password" type="password" autoComplete="current-password" {...register("current_password")} />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="New password" htmlFor="new_password" error={errors.new_password?.message}>
              <Input id="new_password" type="password" autoComplete="new-password" {...register("new_password")} />
            </Field>
            <Field label="Confirm new password" htmlFor="confirm_password" error={errors.confirm_password?.message}>
              <Input id="confirm_password" type="password" autoComplete="new-password" {...register("confirm_password")} />
            </Field>
          </div>
          <div className="flex justify-end">
            <Button type="submit" isLoading={changePassword.isPending}>
              Update password
            </Button>
          </div>
        </form>
      </CardBody>
    </Card>
  );
}

function DemoSection() {
  const resetDemo = useResetDemo();
  const restartTour = useTourStore((s) => s.restart);

  const onReset = () => {
    if (window.confirm("Reset the demo workspace to its original seeded state?")) {
      resetDemo.mutate();
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Demo workspace</CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">
        <p className="text-sm text-muted">
          Restore the demo workspace to its original seeded state, or replay the guided product tour.
        </p>
        {resetDemo.isSuccess && <Alert variant="success">Demo workspace reset. Refreshing your data…</Alert>}
        {resetDemo.isError && <Alert>{getApiErrorMessage(resetDemo.error)}</Alert>}
        <div className="flex flex-wrap gap-3">
          <Button variant="danger" onClick={onReset} isLoading={resetDemo.isPending}>
            Reset demo workspace
          </Button>
          <Button variant="outline" onClick={() => restartTour()}>
            Restart product tour
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}

export default function SettingsPage() {
  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Settings</h1>
        <p className="mt-1 text-sm text-muted">Manage your profile, appearance and preferences.</p>
      </div>
      <AppearanceSection />
      <PreferencesSection />
      <ProfileSection />
      <PasswordSection />
      <SystemSection />
      <DemoSection />
    </div>
  );
}
