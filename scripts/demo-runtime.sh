if [[ -d "$repo/var/interview-demo" && ! -e "$repo/var/demo" ]]; then
  ln -sT interview-demo "$repo/var/demo" || [[ "$repo/var/demo" -ef "$repo/var/interview-demo" ]]
fi
