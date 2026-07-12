"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Field } from "@/components/ui/Field";
import { Alert } from "@/components/ui/Feedback";
import { getApiErrorMessage } from "@/lib/api/client";
import { resetPasswordSchema, type ResetPasswordInput } from "@/lib/validations";
import { useResetPassword } from "@/hooks/useAuth";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const reset = useResetPassword();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ResetPasswordInput>({ resolver: zodResolver(resetPasswordSchema) });

  const onSubmit = (values: ResetPasswordInput) =>
    reset.mutate(
      { token, password: values.new_password },
      { onSuccess: () => setTimeout(() => router.replace("/login"), 1500) },
    );

  if (!token) {
    return (
      <Alert>
        This reset link is missing its token. Please request a new link from the{" "}
        <Link href="/forgot-password" className="underline">
          forgot password
        </Link>{" "}
        page.
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-foreground">Choose a new password</h2>
        <p className="mt-1 text-sm text-muted">Your new password must be at least 8 characters.</p>
      </div>

      {reset.isError && <Alert>{getApiErrorMessage(reset.error, "This reset link is invalid or expired.")}</Alert>}
      {reset.isSuccess && <Alert variant="success">Password reset. Redirecting you to sign in…</Alert>}

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        <Field label="New password" htmlFor="new_password" error={errors.new_password?.message}>
          <Input
            id="new_password"
            type="password"
            autoComplete="new-password"
            placeholder="••••••••"
            hasError={Boolean(errors.new_password)}
            {...register("new_password")}
          />
        </Field>
        <Field label="Confirm password" htmlFor="confirm_password" error={errors.confirm_password?.message}>
          <Input
            id="confirm_password"
            type="password"
            autoComplete="new-password"
            placeholder="••••••••"
            hasError={Boolean(errors.confirm_password)}
            {...register("confirm_password")}
          />
        </Field>
        <Button type="submit" className="w-full" size="lg" isLoading={reset.isPending} disabled={reset.isSuccess}>
          Reset password
        </Button>
      </form>
    </div>
  );
}

export default function ResetPasswordPage() {
  // useSearchParams requires a Suspense boundary during static generation.
  return (
    <Suspense fallback={null}>
      <ResetPasswordForm />
    </Suspense>
  );
}
