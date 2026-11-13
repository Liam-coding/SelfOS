"""Actions HTTP routes; no server imports."""
import json
from pathlib import Path
from urllib.error import URLError

class ActionsRoutes:
    def do_POST(self):
        if not self._local_request():return self._send_json(403,{'error':'Use the local SelfOS dashboard'})
        if not self._auth_guard():return
        if self.path == '/__knowledge_budget__':
            with self.runtime.KNOWLEDGE_RUN_LOCK:
                if self.runtime.KNOWLEDGE_RUN['stop_file'] is not None:
                    return self._send_json(409, {'code':'budget_import_active'})
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 65536: raise ValueError('Invalid budget request size')
                    from selfos.app.budget import save_budget
                    value = save_budget(self.runtime.VAULT, self.runtime.ROOT, json.loads(self._read_body()))
                    return self._send_json(200, value)
                except (ValueError, TypeError, KeyError):
                    return self._send_json(400, {'code':'budget_invalid'})
                except (OSError, RuntimeError):
                    return self._send_json(503, {'code':'budget_unavailable'})
        if self.path == '/__privacy__':
            with self.runtime.KNOWLEDGE_RUN_LOCK:
                if self.runtime.KNOWLEDGE_RUN['stop_file'] is not None:
                    return self._send_json(409, {'code':'privacy_import_active'})
                try:
                    size = int(self.headers.get('Content-Length','0'))
                    if not 0 < size <= 90 * 1024 * 1024: raise ValueError('Invalid package size')
                    body = json.loads(self._read_body())
                    from selfos.app.privacy import privacy_status
                    from selfos.app.migration import export_package, import_package
                    from selfos.sources.selection import save_sources
                    action = body.get('action')
                    if action == 'save':
                        save_sources(self.runtime.VAULT,body['selection'])
                        result = privacy_status(self.runtime.VAULT,self.runtime.ROOT)
                    elif action == 'export':
                        result = export_package(self.runtime.VAULT,self.runtime.ROOT,
                            include_originals=body.get('originals',False),include_backups=body.get('backups',False))
                    elif action == 'import': result = import_package(self.runtime.VAULT,self.runtime.ROOT,body['package'])
                    else: raise ValueError('Invalid privacy action')
                    return self._send_json(200,result)
                except (ValueError,TypeError,KeyError): return self._send_json(400,{'code':'privacy_invalid'})
                except OSError: return self._send_json(503,{'code':'privacy_unavailable'})
        if self.path == '/__onboarding__':
            with self.runtime.KNOWLEDGE_RUN_LOCK:
                if self.runtime.KNOWLEDGE_RUN['stop_file'] is not None:
                    return self._send_json(409, {'code': 'onboarding_import_active'})
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 65536:
                        raise ValueError('Invalid setup request size')
                    body = json.loads(self._read_body())
                    from selfos.app.onboarding import onboarding_action
                    return self._send_json(200, onboarding_action(self.runtime.VAULT, self.runtime.ROOT, body))
                except (ValueError, TypeError, KeyError):
                    return self._send_json(400, {'code': 'onboarding_invalid'})
                except (OSError, RuntimeError):
                    return self._send_json(503, {'code': 'onboarding_unavailable'})
        if self.path=='/__knowledge_correct__':
            with self.runtime.KNOWLEDGE_RUN_LOCK:
                if self.runtime.KNOWLEDGE_RUN['stop_file'] is not None:
                    return self._send_json(409,{'code':'correction_import_active'})
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=65536:raise ValueError('Invalid correction request size')
                    body=json.loads(self._read_body())
                    from selfos.app.corrections import correct_knowledge
                    return self._send_json(200,correct_knowledge(self.runtime.VAULT,body))
                except (ValueError,TypeError,KeyError) as error:
                    message=str(error)
                    code='correction_stale' if 'version' in message else 'correction_dependency' if 'dependent' in message else 'invalid_correction'
                    return self._send_json(409 if code!='invalid_correction' else 400,{'code':code})
                except OSError:
                    return self._send_json(503,{'code':'correction_unavailable'})
        if self.path=='/__model_list__':
            from selfos.providers.client import list_models, ModelListUnsupported
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=32768: raise ValueError('Invalid request size')
                body=json.loads(self._read_body())
                return self._send_json(200,list_models(self.runtime.ROOT,body))
            except ModelListUnsupported:
                return self._send_json(422,{'code':'model_list_unsupported'})
            except (ValueError,TypeError,KeyError):
                return self._send_json(400,{'code':'model_list_invalid'})
            except Exception:
                return self._send_json(502,{'code':'model_list_failed'})
        if self.path in ('/__model_settings__','/__model_test__'):
            with self.runtime.KNOWLEDGE_RUN_LOCK:
                if self.runtime.KNOWLEDGE_RUN['stop_file'] is not None:
                    return self._send_json(409,{'error':'Stop the current import before changing or testing models'})
                try:
                    from selfos.providers.settings import save_config
                    from selfos.providers.client import test_connection
                    body=json.loads(self._read_body())
                    if self.path=='/__model_settings__': result=save_config(self.runtime.ROOT,body)
                    else: result=test_connection(self.runtime.ROOT)
                    return self._send_json(200,result)
                except (ValueError,TypeError,KeyError) as error:
                    return self._send_json(400,{'error':str(error)})
                except RuntimeError as error:
                    return self._send_json(502,{'error':str(error)})
                except Exception:
                    return self._send_json(502,{'error':'Model connection failed; check endpoint, authentication, model and proxy'})
        if self.path in ('/__knowledge_settings__', '/__knowledge_restore__'):
            origin = self.headers.get('Origin')
            host = self.headers.get('Host', '')
            if (origin and origin != f'http://{host}') or self.headers.get('Sec-Fetch-Site') == 'cross-site':
                return self._send_json(403, {'error': 'Use the local SelfOS dashboard'})
            with self.runtime.KNOWLEDGE_RUN_LOCK:
                if self.runtime.KNOWLEDGE_RUN['stop_file'] is not None:
                    return self._send_json(409, {'error': 'Stop the current import before changing settings or restoring'})
                try:
                    body = json.loads(self._read_body())
                    from selfos.storage.settings import save_settings
                    from selfos.app.knowledge import get_status, restore_last
                    if self.path == '/__knowledge_settings__':
                        save_settings(self.runtime.VAULT, body)
                    else:
                        if not isinstance(body.get('operation_id'), str):
                            raise ValueError('operation_id required')
                        restore_last(self.runtime.VAULT, body['operation_id'])
                    return self._send_json(200, get_status(self.runtime.VAULT))
                except (ValueError, TypeError, KeyError) as error:
                    return self._send_json(400, {'error': str(error)})
        if self.path == "/__knowledge_stop__":
            origin = self.headers.get("Origin")
            host = self.headers.get("Host", "")
            if (origin and origin != f"http://{host}") or self.headers.get("Sec-Fetch-Site") == "cross-site":
                return self._send_json(403, {"error": "Stop must be requested from the local dashboard"})
            with self.runtime.KNOWLEDGE_RUN_LOCK:
                marker = self.runtime.KNOWLEDGE_RUN["stop_file"]
                if marker is not None:
                    marker.touch()
            return self._send_json(200, {"ok": True, "running": marker is not None})
        if self.path == "/__harvest__":
            try:
                body = self._read_body()
                full = False
                if body:
                    try:
                        full = json.loads(body).get("full", False)
                    except Exception:
                        pass
                from selfos.app.jobs import command, child_environment
                cmd = command('harvest', self.runtime.ROOT)
                if full:
                    cmd.append("--full")
                result = self.runtime.subprocess.run(
                    cmd,
                    capture_output=True, text=True, timeout=120, cwd=str(self.runtime.ROOT), env=child_environment()
                )
                ok = result.returncode == 0
                self._send_json(200 if ok else 500, {
                    "ok": ok,
                    "stdout": result.stdout[-2000:],
                    "stderr": result.stderr[-500:],
                })
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})

        elif self.path == "/__staging__/apply":
            try:
                body = json.loads(self._read_body())
                filenames = body.get("files", [])  # list of staging filenames to apply
                if not isinstance(filenames,list) or any(not isinstance(name,str) for name in filenames):
                    return self._send_json(400,{'error':'files must be an array of staging filenames'})
                staging_dir = (self.runtime.VAULT / "91_Staging").resolve()
                vault_dir=self.runtime.VAULT.resolve()
                applied = []
                errors = []
                for fname in filenames:
                    if any(char in fname for char in ('/',chr(92),':')) or Path(fname).suffix.casefold()!='.md' or not staging_dir.is_relative_to(vault_dir):
                        errors.append(f'{fname}: invalid staging filename')
                        continue
                    staging_path = (staging_dir / fname).resolve()
                    if staging_path.parent!=staging_dir:
                        errors.append(f'{fname}: staging source leaves its directory')
                        continue
                    if not staging_path.exists():
                        errors.append(f"{fname}: not found")
                        continue
                    text = staging_path.read_text(encoding="utf-8", errors="replace")
                    # parse frontmatter to find target
                    target = ""
                    content_start = 0
                    lines = text.splitlines(keepends=True)
                    if lines and lines[0].strip() == "---":
                        for i, line in enumerate(lines[1:], 1):
                            if line.strip() == "---":
                                content_start = i + 1
                                break
                            if line.startswith("target:"):
                                target = line.split(":", 1)[1].strip()
                    if not target:
                        errors.append(f"{fname}: no target in frontmatter")
                        continue
                    target_path = (self.runtime.ROOT / target).resolve()
                    if Path(target).is_absolute() or ':' in target or not target_path.is_relative_to(vault_dir) or target_path.is_relative_to(staging_dir) or target_path.suffix.casefold()!='.md':
                        errors.append(f'{fname}: target must be canonical markdown inside the vault')
                        continue
                    if any(part.startswith('.') for part in target_path.relative_to(vault_dir).parts):
                        errors.append(f'{fname}: target cannot be an internal vault file')
                        continue
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    # write content after frontmatter
                    content = "".join(lines[content_start:]).lstrip("\n")
                    target_path.write_text(content, encoding="utf-8")
                    staging_path.unlink()
                    applied.append(fname)
                self._send_json(200, {"ok": True, "applied": applied, "errors": errors})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})

        elif self.path == "/chat":
            try:
                body = json.loads(self._read_body())
                messages = body.get("messages", [])
                if not messages:
                    return self._send_json(400, {"error": "messages required"})

                api_key, base_url = self.runtime._get_config()
                if not api_key and __import__('selfos.providers.settings', fromlist=['*']).load_config(self.runtime.ROOT)['provider']=='anthropic':
                    return self._send_json(500, {
                        "error": "ANTHROPIC_API_KEY not set. Add it to .env or export it."
                    })

                reply = self.runtime._call_claude(messages, api_key, base_url)
                self._send_json(200, {"reply": reply})

            except URLError as e:
                self._send_json(502, {"error": f"API error: {e}"})
            except Exception as e:
                self._send_json(500, {"error": str(e)})
        else:
            self._send_json(404, {"error": "not found"})
