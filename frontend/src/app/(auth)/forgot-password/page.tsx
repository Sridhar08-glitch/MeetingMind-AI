"use client";

import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Field } from "@/components/ui/Field";
import { Alert } from "@/components/ui/Feedback";
import { forgotPasswordSchema, type ForgotPasswordInput } from "@/lib/validations";
import { useForgotPassword } from "@/hooks/useAuth";

export default function ForgotPasswordPage() {
  const forgot = useForgotPassword();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ForgotPasswordInput>({ resolver: zodResolver(forgotPasswordSchema) });

  const onSubmit = (values: ForgotPasswordInput) => forgot.mutate(values.email);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-foreground">Reset your password</h2>
        <p className="mt-1 text-sm text-muted">
          Enter your email and we&apos;ll send you a link to reset your password.
        </p>
      </div>

      {forgot.isSuccess ? (
        <Alert variant="success">
          If an account exists for that email, a reset link is on its way. Check your inbox.
        </Alert>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <Field label="Email" htmlFor="email" error={errors.email?.message}>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              placeholder="you@company.com"
              hasError={Boolean(errors.email)}
              {...register("email")}
            />
          </Field>
          <Button type="submit" className="w-full" size="lg" isLoading={forgot.isPending}>
            Send reset link
          </Button>
        </form>
      )}

      <p className="text-center text-sm text-muted">
        <Link href="/login" className="font-medium text-brand-600 hover:text-brand-700">
          Back to sign in
        </Link>
      </p>
    </div>
  );
}
