import { createRouter, RouterProvider } from "@tanstack/react-router";
import { rootRoute } from "./routes/__root";
import { loginRoute } from "./routes/login";
import { mainAflRoute } from "./routes/_authenticated/main-afl";
import { changePasswordRoute } from "./routes/_authenticated/change-password";
import { reportRoute } from "./routes/_authenticated/report";
import { AuthProvider } from "./store/auth";

const routeTree = rootRoute.addChildren([loginRoute, mainAflRoute, changePasswordRoute, reportRoute]);

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
