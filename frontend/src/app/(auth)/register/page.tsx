"use client";

import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Field } from "@/components/ui/Field";
import { Alert } from "@/components/ui/Feedback";
import { getApiErrorMessage } from "@/lib/api/client";
import { registerSchema, type RegisterInput } from "@/lib/validations";
import { useLogin, useRegister } from "@/hooks/useAuth";

export default function RegisterPage() {
  const registerMutation = useRegister();
  const login = useLogin();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterInput>({ resolver: zodResolver(registerSchema) });

  const onSubmit = (values: RegisterInput) => {
    registerMutation.mutate(
      {
        email: values.email,
        password: values.password,
        first_name: values.first_name || undefined,
        last_name: values.last_name || undefined,
      },
      {
        // Seamlessly sign the new user in on success.
        onSuccess: () => login.mutate({ email: values.email, password: values.password }),
      },
    );
  };

  const isBusy = registerMutation.isPending || login.isPending;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-foreground">Create your account</h2>
        <p className="mt-1 text-sm text-muted">Start turning meetings into insight in minutes.</p>
      </div>

      {registerMutation.isError && (
        <Alert>{getApiErrorMessage(registerMutation.error, "Could not create your account.")}</Alert>
      )}

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        <div className="grid grid-cols-2 gap-3">
          <Field label="First name" htmlFor="first_name" error={errors.first_name?.message}>
            <Input id="first_name" placeholder="Alex" {...register("first_name")} />
          </Field>
          <Field label="Last name" htmlFor="last_name" error={errors.last_name?.message}>
            <Input id="last_name" placeholder="Rivera" {...register("last_name")} />
          </Field>
        </div>

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

        <Field
          label="Password"
          htmlFor="password"
          error={errors.password?.message}
          hint="At least 8 characters."
        >
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            placeholder="••••••••"
            hasError={Boolean(errors.password)}
            {...register("password")}
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

        <Button type="submit" className="w-full" size="lg" isLoading={isBusy}>
          Create account
        </Button>
      </form>

      <p className="text-center text-sm text-muted">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-brand-600 hover:text-brand-700">
          Sign in
        </Link>
      </p>
    </div>
  );
}
