import { createRouter, RouterProvider } from "@tanstack/react-router";
import { rootRoute } from "./routes/__root";
import { loginRoute } from "./routes/login";
import { mainAflRoute } from "./routes/_authenticated/main-afl";
import { changePasswordRoute } from "./routes/_authenticated/change-password";
import { dashboardRoute } from "./routes/_authenticated/dashboard";
import { reportsRoute } from "./routes/_authenticated/reports";
import { AuthProvider } from "./store/auth";

const routeTree = rootRoute.addChildren([loginRoute, mainAflRoute, changePasswordRoute, dashboardRoute, reportsRoute]);

const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

export function App() {
  return (
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  );
}
