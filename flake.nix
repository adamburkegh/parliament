{
  description = "Parliament coding agent environment";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-25.05";
    flake-utils.url = "github:numtide/flake-utils";
    jailed-agents.url = "github:andersonjoseph/jailed-agents";
  };

  outputs = { self, nixpkgs, flake-utils, jailed-agents }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };

        # Python environment with just enough to run the agent and tests
        pythonEnv = pkgs.python3.withPackages (ps: with ps; [
          requests  # for llama-server API calls
        ]);

        # Project directory — flake lives inside the repo so this is correct
        projectDir = toString ./.;

        jailedAgent = jailed-agents.lib.${system}.makeJailedAgent {
          name = "parliament-agent";
          pkg = pkgs.writeShellScriptBin "parliament-agent" ''
            cd ${projectDir}
            source .venv/bin/activate 2>/dev/null || true
            python ${projectDir}/agent.py "$@"
          '';
          configPaths = [];
          extraPkgs = [
            pythonEnv
            pkgs.bash
          ];
          extraReadwriteDirs = [ projectDir ];
          extraReadonlyDirs = [
            "${projectDir}/agent.py"
            "${projectDir}/flake.nix"
            "${projectDir}/flake.lock"
            "${projectDir}/requirements.txt"
          ];
          # No network combinator — agent has no network access
          baseJailOptions = 
                with jailed-agents.lib.${system}.internals.jail.combinators; [
            network     # needed to reach llama model server
            time-zone
            no-new-session
            mount-cwd
          ];
        };

      in {
        devShells.default = pkgs.mkShell {
          name = "parliament-dev";

          buildInputs = [
            pythonEnv
            pkgs.git
            jailedAgent
          ];

          shellHook = ''
            export PS1="\[\033[38;5;33m\][parliament]\[\033[0m\] $PS1"

            if [ ! -d .venv ]; then
              echo "Run: python -m venv .venv && pip install -r requirements.txt"
            else
              source .venv/bin/activate
            fi

            export LLAMA_SERVER="http://172.30.84.6:8000/v1"
            export PARLIAMENT_DIR="${projectDir}"

            echo "Parliament agent environment"
            echo "Run 'parliament-agent' to start the jailed agent"
          '';
        };
      }
    );
}

